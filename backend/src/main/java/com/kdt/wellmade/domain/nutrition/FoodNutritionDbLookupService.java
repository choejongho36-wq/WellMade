package com.kdt.wellmade.domain.nutrition;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * DB에 적재된 식약처 표준데이터로 음식명을 검색해서 영양성분을 계산하는 서비스.
 *
 * 매칭 전략 (위에서부터 순서대로 시도, 먼저 맞는 게 있으면 그걸 채택):
 *   1. 요리(data_type='음식')에서 food_name 정확일치                          -> EXACT_PRODUCT
 *   2. 요리에서 representative_food_name(카테고리 통칭) 정확일치              -> EXACT_CATEGORY
 *   3. 가공식품/원재료까지 포함해서 food_name 정확일치                        -> EXACT_PRODUCT
 *   4. 가공식품/원재료까지 포함해서 representative_food_name 정확일치         -> EXACT_CATEGORY
 *   5. 그래도 없으면 food_name에 LIKE 검색으로 폴백                          -> FUZZY
 *   6. nutrition_basis_unit이 "100ml"인 경우 국물류로 보고 100g과 동일하게 근사 처리
 *
 * 요리를 가공식품보다 먼저 보는 이유: 식약처 가공식품 데이터에는 일상 단어와 겹치는 상품명이 있어서
 * (예: "토스트"라는 이름의 탄산음료 750ml) 이름만 보고 고르면 엉뚱한 제품이 확정 매칭돼버림.
 * 같은 이름이 여러 개면 분석값을, 그 다음으로는 이름이 짧아 대표성이 높은 행을 고른다.
 *
 * 인분수로 조회할 때(lookupByServings)는 위 단계로 음식을 먼저 고른 뒤, 그 행에 식품중량이 없으면
 * 같은 음식의 다른 행에서 식품중량이 적힌 걸 찾아 씀. 그것마저 없으면(원재료성 데이터는 식품중량이
 * 아예 없음) 영양성분 기준량 100g으로 넣고 weightEstimated=true로 표시함 - 기록은 되게 하되
 * 프론트가 "추정값이니 그램 수를 고쳐달라"고 안내함.
 *
 * 1~4단계는 신뢰도 높음(자동 확정), 5단계(FUZZY)는 엉뚱한 음식일 수 있어서 호출부가
 * suggestCandidates()로 후보를 뽑아 사용자에게 확인받는 흐름으로 이어짐.
 */
@Service
public class FoodNutritionDbLookupService implements FoodNutritionLookupService {

    private final JdbcTemplate jdbcTemplate;

    public FoodNutritionDbLookupService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public NutritionInfo lookup(String foodName, double amountG) {
        MatchResult match = findBestMatch(foodName);
        if (match == null) {
            return null;
        }
        return buildResult(foodName, match, amountG, false);
    }

    @Override
    public NutritionInfo lookupByServings(String foodName, double servings) {
        MatchResult match = findBestMatch(foodName);
        if (match == null) {
            return null;
        }

        Double referenceWeight = parseWeightReference((String) match.row().get("food_weight_reference"));
        if (referenceWeight == null) {
            // 매칭된 행에 식품중량이 없으면 "같은 음식"의 다른 행 중 중량이 적힌 걸 찾아 그 행으로 계산.
            // 음식 자체를 바꾸지는 않는다 - 중량 조건을 매칭 단계에 섞으면 엉뚱한 음식이 뽑힐 수 있어서
            // (예: 사과 -> 사과파이) 매칭 규칙은 그대로 두고 행만 바꿔 끼운다
            Map<String, Object> weighted = findWeightedRowForSameFood(match.row());
            if (weighted != null) {
                match = new MatchResult(weighted, match.tier());
                referenceWeight = parseWeightReference((String) weighted.get("food_weight_reference"));
            }
        }

        // 원재료성 데이터(농촌진흥청/수산과학원 성분표)는 식품중량이 아예 없음 - 여기서 기록을 실패시키면
        // "사과 1개" 같은 흔한 입력이 막히므로, 영양성분 기준량(전 행 100g/100ml)으로 일단 넣고
        // weightEstimated로 표시해서 사용자가 항목별 그램 수를 고치게 한다
        boolean weightEstimated = referenceWeight == null;
        double baseWeight = weightEstimated ? 100.0 : referenceWeight;
        double amountG = baseWeight * Math.max(servings, 0.1);

        return buildResult(foodName, match, amountG, weightEstimated);
    }

    @Override
    public List<String> suggestCandidates(String foodName, int limit) {
        String escaped = escapeLike(foodName);
        return jdbcTemplate.queryForList("""
                SELECT food_name FROM food_nutrition_reference
                WHERE food_name LIKE ?
                  AND calories IS NOT NULL
                GROUP BY food_name
                ORDER BY MIN(CASE WHEN data_generation_method = '분석' THEN 0 ELSE 1 END),
                         LENGTH(food_name) ASC
                LIMIT ?
                """, String.class, "%" + escaped + "%", limit);
    }

    private NutritionInfo buildResult(String foodName, MatchResult match, double amountG, boolean weightEstimated) {
        Map<String, Object> row = match.row();
        // 100g(또는 100ml 근사) 기준값 -> 실제 섭취량 비율로 환산
        double ratio = amountG / 100.0;

        return new NutritionInfo(
                foodName,
                toDouble(row.get("calories")) * ratio,
                toDouble(row.get("protein_g")) * ratio,
                toDouble(row.get("carbs_g")) * ratio,
                toDouble(row.get("fat_g")) * ratio,
                amountG,
                match.tier(),
                weightEstimated
        );
    }

    private MatchResult findBestMatch(String foodName) {
        // 1) 요리(data_type='음식')에서 먼저 찾는다 - "토스트"처럼 흔한 음식 이름이 같은 이름의
        //    가공식품(음료 "토스트" 750ml)에 걸리는 걸 막기 위함. 제품명을 정확히 말한 경우는
        //    아래 가공식품 단계나 LIKE 폴백에서 잡힌다
        MatchResult dish = findExactMatch(foodName, true);
        if (dish != null) {
            return dish;
        }

        // 2) 요리에 없으면 가공식품/원재료까지 포함해서 정확일치 검색
        MatchResult product = findExactMatch(foodName, false);
        if (product != null) {
            return product;
        }

        // 3) 폴백: food_name에 LIKE 검색 - 분석값 우선, 그다음 이름이 짧아 검색어에 더 가까운 것 우선
        String escapedFoodName = escapeLike(foodName);
        List<Map<String, Object>> likeMatch = jdbcTemplate.queryForList("""
                SELECT * FROM food_nutrition_reference
                WHERE food_name LIKE ?
                  AND calories IS NOT NULL
                ORDER BY CASE WHEN data_generation_method = '분석' THEN 0 ELSE 1 END,
                         LENGTH(food_name) ASC
                LIMIT 1
                """, "%" + escapedFoodName + "%");
        if (!likeMatch.isEmpty()) {
            return new MatchResult(likeMatch.get(0), MatchTier.FUZZY);
        }

        return null; // 못 찾음 - 호출부에서 "이 음식은 DB에 없어요" 처리 필요
    }

    /**
     * 식품명 -> 대표식품명 순으로 정확일치를 찾음. 같은 이름이 여럿이면 분석값을, 그 다음으로는
     * 이름이 짧은(덜 구체적이라 대표성이 높은) 행을 고른다.
     *
     * @param dishOnly true면 요리 데이터(data_type='음식')만 대상으로 함
     */
    private MatchResult findExactMatch(String foodName, boolean dishOnly) {
        // 고정 문자열이라 인젝션 여지 없음 (검색어는 바인딩 파라미터로만 들어감)
        String dishFilter = dishOnly ? "AND data_type = '음식'" : "";

        List<Map<String, Object>> byFoodName =
                jdbcTemplate.queryForList(EXACT_MATCH_SQL.formatted("food_name", dishFilter), foodName);
        if (!byFoodName.isEmpty()) {
            return new MatchResult(byFoodName.get(0), MatchTier.EXACT_PRODUCT);
        }

        List<Map<String, Object>> byRepName =
                jdbcTemplate.queryForList(EXACT_MATCH_SQL.formatted("representative_food_name", dishFilter), foodName);
        if (!byRepName.isEmpty()) {
            return new MatchResult(byRepName.get(0), MatchTier.EXACT_CATEGORY);
        }
        return null;
    }

    /** %s 자리에는 코드에 고정된 컬럼명/필터만 들어감 (검색어는 바인딩 파라미터) */
    private static final String EXACT_MATCH_SQL = """
            SELECT * FROM food_nutrition_reference
            WHERE %s = ?
              AND calories IS NOT NULL
              %s
            ORDER BY CASE WHEN data_generation_method = '분석' THEN 0 ELSE 1 END,
                     LENGTH(food_name) ASC
            LIMIT 1
            """;

    /**
     * 매칭된 행에 식품중량이 없을 때, 같은 음식(같은 식품명 -> 없으면 같은 대표식품명)의 행 중에서
     * 식품중량이 적힌 행을 찾아옴. 영양성분도 그 행 값을 쓰므로 중량과 성분이 같은 레코드에서 나온다.
     */
    private Map<String, Object> findWeightedRowForSameFood(Map<String, Object> row) {
        List<Map<String, Object>> byFoodName =
                jdbcTemplate.queryForList(WEIGHTED_ROW_SQL.formatted("food_name"), row.get("food_name"));
        if (!byFoodName.isEmpty()) {
            return byFoodName.get(0);
        }
        String repName = (String) row.get("representative_food_name");
        if (repName == null || repName.isBlank()) {
            return null;
        }
        List<Map<String, Object>> byRepName =
                jdbcTemplate.queryForList(WEIGHTED_ROW_SQL.formatted("representative_food_name"), repName);
        return byRepName.isEmpty() ? null : byRepName.get(0);
    }

    /** %s 자리에는 코드에 고정된 컬럼명만 들어감 (검색어는 바인딩 파라미터) */
    private static final String WEIGHTED_ROW_SQL = """
            SELECT * FROM food_nutrition_reference
            WHERE %s = ?
              AND calories IS NOT NULL
              AND food_weight_reference REGEXP '[0-9]'
            ORDER BY CASE WHEN data_generation_method = '분석' THEN 0 ELSE 1 END
            LIMIT 1
            """;

    private String escapeLike(String raw) {
        return raw.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_");
    }

    /**
     * food_weight_reference는 식약처 원본 필드(식품중량)를 그대로 텍스트로 적재해둔 컬럼이라
     * "200", "200g", "1인분(200g)"처럼 형식이 제각각임. 숫자만 뽑아서 그램으로 씀 - 숫자를
     * 못 찾으면(값이 없거나 형식이 이상하면) null을 반환해서 호출부가 기본값으로 폴백하게 함.
     */
    private Double parseWeightReference(String raw) {
        if (raw == null || raw.isBlank()) {
            return null;
        }
        Matcher matcher = Pattern.compile("(\\d+(\\.\\d+)?)").matcher(raw);
        if (!matcher.find()) {
            return null;
        }
        try {
            double value = Double.parseDouble(matcher.group(1));
            return value > 0 ? value : null;
        } catch (NumberFormatException e) {
            return null;
        }
    }

    private double toDouble(Object value) {
        if (value == null) return 0.0;
        if (value instanceof BigDecimal bd) return bd.doubleValue();
        return Double.parseDouble(value.toString());
    }

    private record MatchResult(Map<String, Object> row, MatchTier tier) {}
}

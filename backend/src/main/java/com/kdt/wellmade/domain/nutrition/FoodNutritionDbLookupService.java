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
 * MockFoodNutritionLookupService를 대체함 - FoodNutritionLookupService 인터페이스는 동일하므로
 * 이 코드를 쓰는 다른 클래스(MealParsingTestController 등)는 수정할 필요 없음.
 *
 * 매칭 전략 (위에서부터 순서대로 시도, 먼저 맞는 게 있으면 그걸 채택):
 *   1. food_name(구체적 제품명, 예: "포카칩 오리지널")이 정확히 일치 + 분석값 우선  -> EXACT_PRODUCT
 *      -> "포카칩"처럼 특정 브랜드/제품명을 검색할 때 대표식품명(카테고리)보다 먼저 확인해야
 *         엉뚱한 카테고리의 다른 제품으로 잘못 매칭되는 걸 막을 수 있음
 *   2. food_name 정확히 일치, 분석값 없으면 아무거나                              -> EXACT_PRODUCT
 *   3. representative_food_name(카테고리 통칭, 예: "김치찌개")이 정확히 일치 + 분석값 우선 -> EXACT_CATEGORY
 *   4. representative_food_name 정확히 일치, 분석값 없으면 아무거나                -> EXACT_CATEGORY
 *   5. 그래도 없으면 food_name에 LIKE 검색으로 폴백 - 분석값 우선, 이름 길이가 짧아
 *      검색어에 더 가까운(덜 구체적인 다른 옵션이 섞여 들어갈 여지가 적은) 항목 우선   -> FUZZY
 *   6. nutrition_basis_unit이 "100ml"인 경우 국물류로 보고 100g과 동일하게 근사 처리
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
        boolean weightEstimated = referenceWeight == null;
        // 기준중량이 없으면 영양성분 기준량(보통 100g/100ml)을 1인분으로 간주 - 완전히 틀린 값보다는
        // "DB에 있는 값 기준"이 낫고, weightEstimated=true로 표시해서 프론트가 추정임을 알려줌
        double baseWeight = referenceWeight != null ? referenceWeight : 100.0;
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
        // 1) 식품명(구체적 제품명) 정확 일치 + 분석값 우선
        List<Map<String, Object>> exactFoodNameAnalyzed = jdbcTemplate.queryForList("""
                SELECT * FROM food_nutrition_reference
                WHERE food_name = ?
                  AND data_generation_method = '분석'
                  AND calories IS NOT NULL
                LIMIT 1
                """, foodName);
        if (!exactFoodNameAnalyzed.isEmpty()) {
            return new MatchResult(exactFoodNameAnalyzed.get(0), MatchTier.EXACT_PRODUCT);
        }

        // 2) 식품명 정확 일치, 분석값 없으면 아무거나
        List<Map<String, Object>> exactFoodNameAny = jdbcTemplate.queryForList("""
                SELECT * FROM food_nutrition_reference
                WHERE food_name = ?
                  AND calories IS NOT NULL
                LIMIT 1
                """, foodName);
        if (!exactFoodNameAny.isEmpty()) {
            return new MatchResult(exactFoodNameAny.get(0), MatchTier.EXACT_PRODUCT);
        }

        // 3) 대표식품명(카테고리) 정확 일치 + 분석값 우선
        List<Map<String, Object>> exactRepAnalyzed = jdbcTemplate.queryForList("""
                SELECT * FROM food_nutrition_reference
                WHERE representative_food_name = ?
                  AND data_generation_method = '분석'
                  AND calories IS NOT NULL
                LIMIT 1
                """, foodName);
        if (!exactRepAnalyzed.isEmpty()) {
            return new MatchResult(exactRepAnalyzed.get(0), MatchTier.EXACT_CATEGORY);
        }

        // 4) 대표식품명 정확 일치, 분석값 없으면 아무거나
        List<Map<String, Object>> exactRepAny = jdbcTemplate.queryForList("""
                SELECT * FROM food_nutrition_reference
                WHERE representative_food_name = ?
                  AND calories IS NOT NULL
                LIMIT 1
                """, foodName);
        if (!exactRepAny.isEmpty()) {
            return new MatchResult(exactRepAny.get(0), MatchTier.EXACT_CATEGORY);
        }

        // 5) 폴백: food_name에 LIKE 검색 - 분석값 우선, 그다음 이름이 짧아 검색어에 더 가까운 것 우선
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

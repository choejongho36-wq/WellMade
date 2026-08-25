package com.kdt.wellmade.domain.nutrition;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
 
import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
 
/**
 * DB에 적재된 식약처 표준데이터로 음식명을 검색해서 영양성분을 계산하는 서비스.
 * MockFoodNutritionLookupService를 대체함 - FoodNutritionLookupService 인터페이스는 동일하므로
 * 이 코드를 쓰는 다른 클래스(MealParsingTestController 등)는 수정할 필요 없음.
 *
 * 매칭 전략:
 *   1. representative_food_name 정확히 일치하는 항목 우선 검색
 *   2. 여러 건이면 data_generation_method = '분석'(측정값, 가장 신뢰도 높음) 우선 채택
 *   3. 정확히 일치하는 게 없으면 food_name에 LIKE 검색으로 폴백
 *   4. nutrition_basis_unit이 "100ml"인 경우 국물류로 보고 100g과 동일하게 근사 처리
 */
@Service
public class FoodNutritionDbLookupService implements FoodNutritionLookupService {
 
    private final JdbcTemplate jdbcTemplate;
 
    public FoodNutritionDbLookupService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }
 
    @Override
    public NutritionInfo lookup(String foodName, double amountG) {
        Map<String, Object> row = findBestMatch(foodName);
        if (row == null) {
            return null;
        }
 
        // 100g(또는 100ml 근사) 기준값 -> 실제 섭취량 비율로 환산
        double ratio = amountG / 100.0;
 
        return new NutritionInfo(
                foodName,
                toDouble(row.get("calories")) * ratio,
                toDouble(row.get("protein_g")) * ratio,
                toDouble(row.get("carbs_g")) * ratio,
                toDouble(row.get("fat_g")) * ratio
        );
    }
 
    private Map<String, Object> findBestMatch(String foodName) {
        // 1) 대표식품명 정확 일치 + 분석값 우선
        String exactAnalyzedSql = """
                SELECT * FROM food_nutrition_reference
                WHERE representative_food_name = ?
                  AND data_generation_method = '분석'
                  AND calories IS NOT NULL
                LIMIT 1
                """;
        List<Map<String, Object>> exactAnalyzed = jdbcTemplate.queryForList(exactAnalyzedSql, foodName);
        if (!exactAnalyzed.isEmpty()) {
            return exactAnalyzed.get(0);
        }
 
        // 2) 대표식품명 정확 일치, 분석값 없으면 아무거나
        String exactAnySql = """
                SELECT * FROM food_nutrition_reference
                WHERE representative_food_name = ?
                  AND calories IS NOT NULL
                LIMIT 1
                """;
        List<Map<String, Object>> exactAny = jdbcTemplate.queryForList(exactAnySql, foodName);
        if (!exactAny.isEmpty()) {
            return exactAny.get(0);
        }
 
        // 3) 폴백: food_name에 LIKE 검색
        String likeSql = """
                SELECT * FROM food_nutrition_reference
                WHERE food_name LIKE ?
                  AND calories IS NOT NULL
                ORDER BY CASE WHEN data_generation_method = '분석' THEN 0 ELSE 1 END
                LIMIT 1
                """;
        String escapedFoodName = foodName.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_");
        List<Map<String, Object>> likeMatch = jdbcTemplate.queryForList(likeSql, "%" + escapedFoodName + "%");
        if (!likeMatch.isEmpty()) {
            return likeMatch.get(0);
        }
 
        return null; // 못 찾음 - 호출부에서 "이 음식은 DB에 없어요" 처리 필요
    }
 
    private double toDouble(Object value) {
        if (value == null) return 0.0;
        if (value instanceof BigDecimal bd) return bd.doubleValue();
        return Double.parseDouble(value.toString());
    }
}
 
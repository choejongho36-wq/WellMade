package com.kdt.wellmade.domain.nutrition;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.time.LocalDate;
import java.time.LocalTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
 
/**
 * "오늘 뭐 먹었는지" 기록하고 조회하는 서비스.
 *
 * 흐름:
 *   1. 사용자가 메뉴 텍스트 전송 (예: "점심에 김치찌개랑 밥 한공기 먹었어요")
 *   2. FoodParsingService(Qwen)가 음식항목+양으로 파싱
 *   3. FoodNutritionLookupService(식약처 DB)가 항목별 영양성분 조회
 *   4. 합산해서 diet_meals에 한 줄로 저장 (raw_message, food_items, kcal, protein_g 등)
 *   5. 오늘 날짜로 저장된 것들을 조회/합산해서 하루 총량 확인 가능
 *
 * *** diet_plans(목표 설정) 없이도 동작함 - 순수 기록/조회 용도 ***
 */
@Service
public class MealLoggingService {
 
    private final FoodParsingService foodParsingService;
    private final FoodNutritionLookupService nutritionLookupService;
    private final JdbcTemplate jdbcTemplate;
    private final ObjectMapper objectMapper = new ObjectMapper();
 
    public MealLoggingService(
            FoodParsingService foodParsingService,
            FoodNutritionLookupService nutritionLookupService,
            JdbcTemplate jdbcTemplate
    ) {
        this.foodParsingService = foodParsingService;
        this.nutritionLookupService = nutritionLookupService;
        this.jdbcTemplate = jdbcTemplate;
    }
 
    /**
     * 메뉴 텍스트를 파싱+조회해서 diet_meals에 한 줄로 저장.
     *
     * @param userId     사용자 ID
     * @param rawMessage 사용자가 보낸 원문 메시지
     * @param mealType   "BREAKFAST"/"LUNCH"/"DINNER"/"SNACK" - null이면 현재 시각 기준으로 자동 추정
     * @return 저장된 결과 (합산 영양성분 + 인식 못 한 음식 목록)
     */
    public MealLogResult logMeal(Long userId, String rawMessage, String mealType) {
        List<FoodParsingService.FoodItem> parsedItems = foodParsingService.parse(rawMessage);

        double totalCalories = 0, totalProtein = 0, totalCarbs = 0, totalFat = 0;
        List<Map<String, Object>> foodItemsForJson = new ArrayList<>();
        List<String> notFound = new ArrayList<>();

        for (FoodParsingService.FoodItem item : parsedItems) {
            if (item.amountG() <= 0) {
                notFound.add(item.foodName());
                continue;
            }

            FoodNutritionLookupService.NutritionInfo info =
                    nutritionLookupService.lookup(item.foodName(), item.amountG());

            if (info == null) {
                notFound.add(item.foodName());
                continue;
            }
 
            totalCalories += info.calories();
            totalProtein += info.proteinG();
            totalCarbs += info.carbsG();
            totalFat += info.fatG();
 
            foodItemsForJson.add(Map.of(
                    "foodName", item.foodName(),
                    "amountG", item.amountG(),
                    "calories", Math.round(info.calories() * 10) / 10.0
            ));
        }
 
        String resolvedMealType = (mealType != null) ? mealType : inferMealTypeByTime();
        String foodItemsJson = toJson(foodItemsForJson);
        String menuNameSummary = summarizeMenuNames(parsedItems);
 
        jdbcTemplate.update("""
                INSERT INTO diet_meals
                (user_id, logged_date, meal_type, menu_name, raw_message,
                 kcal, protein_g, carbs_g, fat_g, food_items)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                userId, LocalDate.now(), resolvedMealType, menuNameSummary, rawMessage,
                Math.round(totalCalories), totalProtein, totalCarbs, totalFat, foodItemsJson
        );
 
        return new MealLogResult(
                menuNameSummary, resolvedMealType,
                totalCalories, totalProtein, totalCarbs, totalFat,
                notFound
        );
    }
 
    /** 오늘 기록된 끼니 목록 (시간순) */
    public List<Map<String, Object>> getTodayMeals(Long userId) {
        return jdbcTemplate.queryForList("""
                SELECT id, meal_type, menu_name, raw_message, kcal, protein_g, carbs_g, fat_g, created_at
                FROM diet_meals
                WHERE user_id = ? AND logged_date = ?
                ORDER BY created_at ASC
                """, userId, LocalDate.now());
    }
 
    /** 오늘 하루 총 칼로리/영양소 합계 */
    public DailyTotal getTodayTotal(Long userId) {
        Map<String, Object> row = jdbcTemplate.queryForMap("""
                SELECT
                    COALESCE(SUM(kcal), 0) AS total_kcal,
                    COALESCE(SUM(protein_g), 0) AS total_protein,
                    COALESCE(SUM(carbs_g), 0) AS total_carbs,
                    COALESCE(SUM(fat_g), 0) AS total_fat,
                    COUNT(*) AS meal_count
                FROM diet_meals
                WHERE user_id = ? AND logged_date = ?
                """, userId, LocalDate.now());
 
        return new DailyTotal(
                ((Number) row.get("total_kcal")).doubleValue(),
                ((Number) row.get("total_protein")).doubleValue(),
                ((Number) row.get("total_carbs")).doubleValue(),
                ((Number) row.get("total_fat")).doubleValue(),
                ((Number) row.get("meal_count")).intValue()
        );
    }
 
    private String inferMealTypeByTime() {
        int hour = LocalTime.now().getHour();
        if (hour < 11) return "BREAKFAST";
        if (hour < 15) return "LUNCH";
        if (hour < 21) return "DINNER";
        return "SNACK";
    }
 
    private String summarizeMenuNames(List<FoodParsingService.FoodItem> items) {
        return items.stream()
                .map(FoodParsingService.FoodItem::foodName)
                .reduce((a, b) -> a + ", " + b)
                .orElse("(인식된 음식 없음)");
    }
 
    private String toJson(Object obj) {
        try {
            return objectMapper.writeValueAsString(obj);
        } catch (Exception e) {
            e.printStackTrace();
            return "[]";
        }
    }
 
    public record MealLogResult(
            String menuNameSummary,
            String mealType,
            double totalCalories,
            double totalProteinG,
            double totalCarbsG,
            double totalFatG,
            List<String> notFoundFoods
    ) {}
 
    public record DailyTotal(
            double totalCalories,
            double totalProteinG,
            double totalCarbsG,
            double totalFatG,
            int mealCount
    ) {}
}
 
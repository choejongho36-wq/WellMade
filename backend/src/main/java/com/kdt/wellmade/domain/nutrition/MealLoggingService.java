package com.kdt.wellmade.domain.nutrition;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.time.LocalDate;
import java.time.LocalTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
 
/**
 * "오늘 뭐 먹었는지" 기록하고 조회하는 서비스.
 *
 * 흐름:
 *   1. 사용자가 메뉴 텍스트 전송 (예: "점심에 김치찌개랑 밥 한공기 먹었어요")
 *   2. FoodParsingService(Qwen)가 음식항목+양으로 파싱
 *   3. FoodNutritionLookupService(식약처 DB)가 항목별 영양성분 조회
 *   4. 매칭된 항목들만 합산해서 diet_meals에 한 줄로 저장 (raw_message, food_items, kcal, protein_g 등)
 *      매칭 안 된 항목은 저장하지 않고 notFoundFoods로 별도 안내함 (전부-아니면-무 저장 방지)
 *   5. 오늘 날짜로 저장된 것들을 조회/합산해서 하루 총량 확인 가능
 *
 * *** diet_plans(목표 설정) 없이도 동작함 - 순수 기록/조회 용도 ***
 */
@Service
public class MealLoggingService {

    private static final Logger log = LoggerFactory.getLogger(MealLoggingService.class);
 
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
     * 항목 중 일부만 DB 매칭에 실패해도 나머지는 저장하고, 실패한 항목만 notFoundFoods로 안내함
     * (예전엔 하나라도 실패하면 전체를 버렸음).
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

        if (parsedItems.isEmpty()) {
            notFound.add(rawMessage);
        }

        for (FoodParsingService.FoodItem item : parsedItems) {
            if (item.amountG() <= 0) {
                notFound.add(item.foodName());
                continue;
            }

            FoodNutritionLookupService.NutritionInfo info =
                    nutritionLookupService.lookup(item.searchName(), item.amountG());

            if (info == null) {
                notFound.add(item.foodName());
                continue;
            }
 
            totalCalories += info.calories();
            totalProtein += info.proteinG();
            totalCarbs += info.carbsG();
            totalFat += info.fatG();
 
            // searchName도 같이 저장해둠 - 나중에 그램 수를 수정할 때 같은 이름으로 다시 조회해야 하는데
            // foodName(사용자가 말한 그대로, 예: "포카칩 큰 봉지")으로는 DB 재검색이 안 될 수 있어서
            foodItemsForJson.add(item(item.foodName(), item.searchName(), item.amountG(), info));
        }

        if (foodItemsForJson.isEmpty()) {
            // 매칭된 게 하나도 없을 때만 저장할 게 없으므로 여기서 끝냄
            return new MealLogResult(null, null, 0, 0, 0, 0, notFound);
        }

        String resolvedMealType = (mealType != null) ? mealType : inferMealTypeByTime();
        String foodItemsJson = toJson(foodItemsForJson);
        String menuNameSummary = summarizeMenuNames(foodItemsForJson);

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
 
    /** 특정 날짜에 기록된 끼니 목록 (시간순). food_items에 항목별 이름/그램/칼로리가 JSON 배열로 들어있음 */
    public List<Map<String, Object>> getMealsForDate(Long userId, LocalDate date) {
        return jdbcTemplate.queryForList("""
                SELECT id, meal_type, menu_name, raw_message, kcal, protein_g, carbs_g, fat_g,
                       food_items, created_at
                FROM diet_meals
                WHERE user_id = ? AND logged_date = ?
                ORDER BY created_at ASC
                """, userId, date);
    }

    /** 특정 날짜의 총 칼로리/영양소 합계 */
    public DailyTotal getTotalForDate(Long userId, LocalDate date) {
        Map<String, Object> row = jdbcTemplate.queryForMap("""
                SELECT
                    COALESCE(SUM(kcal), 0) AS total_kcal,
                    COALESCE(SUM(protein_g), 0) AS total_protein,
                    COALESCE(SUM(carbs_g), 0) AS total_carbs,
                    COALESCE(SUM(fat_g), 0) AS total_fat,
                    COUNT(*) AS meal_count
                FROM diet_meals
                WHERE user_id = ? AND logged_date = ?
                """, userId, date);
 
        return new DailyTotal(
                ((Number) row.get("total_kcal")).doubleValue(),
                ((Number) row.get("total_protein")).doubleValue(),
                ((Number) row.get("total_carbs")).doubleValue(),
                ((Number) row.get("total_fat")).doubleValue(),
                ((Number) row.get("meal_count")).intValue()
        );
    }
 
    /** 기록 수정 - 끼니 종류/메뉴명/칼로리만 직접 고칠 때 (본인 소유 레코드만) */
    public void updateMeal(Long userId, Long mealId, String mealType, String menuName, double kcal) {
        int updated = jdbcTemplate.update("""
                UPDATE diet_meals
                SET meal_type = ?, menu_name = ?, kcal = ?
                WHERE id = ? AND user_id = ?
                """, mealType, menuName, Math.round(kcal), mealId, userId);

        if (updated == 0) {
            throw new IllegalArgumentException("수정할 기록을 찾을 수 없습니다.");
        }
    }

    /**
     * food_items 배열 중 한 항목의 그램 수를 고쳐서, 그 항목만 영양정보를 다시 조회하고
     * 끼니 전체 합계(kcal/protein/carbs/fat)를 재계산해서 반영함 (본인 소유 레코드만).
     *
     * @param itemIndex food_items 배열에서의 0부터 시작하는 인덱스
     */
    public MealItemUpdateResult updateMealItemAmount(Long userId, Long mealId, int itemIndex, double newAmountG) {
        if (newAmountG <= 0) {
            throw new IllegalArgumentException("그램 수는 0보다 커야 합니다.");
        }

        Map<String, Object> row;
        try {
            row = jdbcTemplate.queryForMap(
                    "SELECT food_items FROM diet_meals WHERE id = ? AND user_id = ?", mealId, userId);
        } catch (EmptyResultDataAccessException e) {
            throw new IllegalArgumentException("수정할 기록을 찾을 수 없습니다.");
        }

        List<Map<String, Object>> items = parseFoodItemsJson((String) row.get("food_items"));
        if (itemIndex < 0 || itemIndex >= items.size()) {
            throw new IllegalArgumentException("수정할 항목을 찾을 수 없습니다.");
        }

        Map<String, Object> target = items.get(itemIndex);
        String foodName = (String) target.get("foodName");
        // 이 패치 이전에 저장된 기록은 searchName이 없을 수 있어서, 없으면 foodName으로 재조회 시도
        String searchName = target.get("searchName") != null ? (String) target.get("searchName") : foodName;

        FoodNutritionLookupService.NutritionInfo info = nutritionLookupService.lookup(searchName, newAmountG);
        if (info == null) {
            throw new IllegalArgumentException("해당 음식을 다시 조회하지 못했어요.");
        }

        items.set(itemIndex, item(foodName, searchName, newAmountG, info));

        double totalCalories = 0, totalProtein = 0, totalCarbs = 0, totalFat = 0;
        for (Map<String, Object> it : items) {
            totalCalories += toDouble(it.get("calories"));
            totalProtein += toDouble(it.get("proteinG"));
            totalCarbs += toDouble(it.get("carbsG"));
            totalFat += toDouble(it.get("fatG"));
        }

        jdbcTemplate.update("""
                UPDATE diet_meals
                SET kcal = ?, protein_g = ?, carbs_g = ?, fat_g = ?, food_items = ?
                WHERE id = ? AND user_id = ?
                """,
                Math.round(totalCalories), totalProtein, totalCarbs, totalFat, toJson(items),
                mealId, userId
        );

        return new MealItemUpdateResult(items, totalCalories, totalProtein, totalCarbs, totalFat);
    }

    /** 기록 삭제 (본인 소유 레코드만) */
    public void deleteMeal(Long userId, Long mealId) {
        int deleted = jdbcTemplate.update(
                "DELETE FROM diet_meals WHERE id = ? AND user_id = ?", mealId, userId);

        if (deleted == 0) {
            throw new IllegalArgumentException("삭제할 기록을 찾을 수 없습니다.");
        }
    }

    private String inferMealTypeByTime() {
        int hour = LocalTime.now().getHour();
        if (hour < 11) return "BREAKFAST";
        if (hour < 15) return "LUNCH";
        if (hour < 21) return "DINNER";
        return "SNACK";
    }
 
    /** DB 매칭까지 성공한 항목만으로 메뉴명을 요약 (못 찾은 항목은 notFound로 따로 안내) */
    private String summarizeMenuNames(List<Map<String, Object>> foodItemsForJson) {
        return foodItemsForJson.stream()
                .map(m -> (String) m.get("foodName"))
                .reduce((a, b) -> a + ", " + b)
                .orElse("(인식된 음식 없음)");
    }

    private Map<String, Object> item(
            String foodName, String searchName, double amountG, FoodNutritionLookupService.NutritionInfo info
    ) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("foodName", foodName);
        m.put("searchName", searchName);
        m.put("amountG", amountG);
        m.put("calories", round1(info.calories()));
        m.put("proteinG", round1(info.proteinG()));
        m.put("carbsG", round1(info.carbsG()));
        m.put("fatG", round1(info.fatG()));
        return m;
    }

    private double round1(double v) {
        return Math.round(v * 10) / 10.0;
    }

    private double toDouble(Object v) {
        return v instanceof Number n ? n.doubleValue() : 0.0;
    }

    /** food_items 컬럼(JSON 문자열)을 Map 리스트로 파싱. 값이 없거나 비어있으면 빈 리스트 */
    private List<Map<String, Object>> parseFoodItemsJson(String json) {
        if (json == null || json.isBlank()) {
            return new ArrayList<>();
        }
        try {
            JsonNode array = objectMapper.readTree(json);
            List<Map<String, Object>> items = new ArrayList<>();
            for (JsonNode node : array) {
                Map<String, Object> m = new LinkedHashMap<>();
                node.fields().forEachRemaining(entry -> {
                    JsonNode v = entry.getValue();
                    m.put(entry.getKey(), v.isNumber() ? v.asDouble() : v.asText());
                });
                items.add(m);
            }
            return items;
        } catch (Exception e) {
            log.error("food_items JSON 파싱 실패. 원문: {}", json, e);
            throw new IllegalArgumentException("기존 기록을 읽는 중 문제가 생겼어요.");
        }
    }
 
    private String toJson(Object obj) {
        try {
            return objectMapper.writeValueAsString(obj);
        } catch (Exception e) {
            log.error("food_items 직렬화 실패", e);
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

    public record MealItemUpdateResult(
            List<Map<String, Object>> foodItems,
            double totalCalories,
            double totalProteinG,
            double totalCarbsG,
            double totalFatG
    ) {}
}
 
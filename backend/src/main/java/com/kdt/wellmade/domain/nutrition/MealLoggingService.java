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
 *   2. FoodParsingService(Qwen)가 음식항목 + (그램 또는 인분수)로 파싱
 *      - 그램수는 되도록 Qwen이 상상하지 않고, DB의 1인분 기준중량 × 인분수로 서버가 계산함
 *   3. 검색어를 이 사용자가 예전에 직접 골라둔 매칭이 있으면(UserFoodAliasService) 그 이름으로 치환
 *   4. FoodNutritionLookupService(식약처 DB)가 항목별 영양성분 조회 - 몇 단계에서 매칭됐는지(MatchTier)도 같이 옴
 *   5. 매칭된 항목들만 합산해서 diet_meals에 한 줄로 저장 (raw_message, food_items, kcal, protein_g 등)
 *      매칭 안 된 항목은 저장하지 않고 notFoundFoods로 별도 안내함 (전부-아니면-무 저장 방지)
 *      LIKE 폴백(FUZZY)으로만 매칭된 항목은 후보 목록(candidates)도 같이 저장해서, 프론트가
 *      "이걸로 인식했어요, 아니면 다른 후보를 골라주세요" 배지를 보여줄 수 있게 함
 *   6. 오늘 날짜로 저장된 것들을 조회/합산해서 하루 총량 확인 가능
 *
 * *** diet_plans(목표 설정) 없이도 동작함 - 순수 기록/조회 용도 ***
 */
@Service
public class MealLoggingService {

    private static final Logger log = LoggerFactory.getLogger(MealLoggingService.class);
 
    private final FoodParsingService foodParsingService;
    private final FoodNutritionLookupService nutritionLookupService;
    private final UserFoodAliasService foodAliasService;
    private final JdbcTemplate jdbcTemplate;
    private final ObjectMapper objectMapper = new ObjectMapper();
 
    public MealLoggingService(
            FoodParsingService foodParsingService,
            FoodNutritionLookupService nutritionLookupService,
            UserFoodAliasService foodAliasService,
            JdbcTemplate jdbcTemplate
    ) {
        this.foodParsingService = foodParsingService;
        this.nutritionLookupService = nutritionLookupService;
        this.foodAliasService = foodAliasService;
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
            String searchName = resolveSearchName(userId, item.foodName(), item.searchName());

            FoodNutritionLookupService.NutritionInfo info = (item.amountG() != null && item.amountG() > 0)
                    // 사용자가 그램을 직접 말한 경우 - 그 값 그대로
                    ? nutritionLookupService.lookup(searchName, item.amountG())
                    // 인분수만 말한 경우 - DB 표준중량 × 인분수로 서버가 환산
                    : nutritionLookupService.lookupByServings(searchName, item.servings());

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
            foodItemsForJson.add(item(item.foodName(), searchName, info, candidatesIfUnsure(searchName, info)));
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
 
    /**
     * 특정 날짜에 기록된 끼니 목록. 입력한 순서가 아니라 아침 -> 점심 -> 저녁 순으로 정렬하고,
     * 간식은 위치가 중요하지 않아 맨 뒤로 보냄 (같은 끼니 종류끼리는 기록한 시간순).
     * food_items에 항목별 이름/그램/칼로리가 JSON 배열로 들어있음
     */
    public List<Map<String, Object>> getMealsForDate(Long userId, LocalDate date) {
        return jdbcTemplate.queryForList("""
                SELECT id, meal_type, menu_name, raw_message, kcal, protein_g, carbs_g, fat_g,
                       food_items, created_at
                FROM diet_meals
                WHERE user_id = ? AND logged_date = ?
                ORDER BY CASE meal_type
                             WHEN 'BREAKFAST' THEN 0
                             WHEN 'LUNCH' THEN 1
                             WHEN 'DINNER' THEN 2
                             ELSE 3
                         END,
                         created_at ASC
                """, userId, date);
    }

    /** 특정 연/월의 날짜별 칼로리 합계 (달력 칸에 표시할 용도). 기록 없는 날짜는 포함하지 않음 */
    public Map<String, Double> getDailyCaloriesForMonth(Long userId, int year, int month) {
        LocalDate start = LocalDate.of(year, month, 1);
        LocalDate end = start.withDayOfMonth(start.lengthOfMonth());

        List<Map<String, Object>> rows = jdbcTemplate.queryForList("""
                SELECT logged_date, SUM(kcal) AS total_kcal
                FROM diet_meals
                WHERE user_id = ? AND logged_date BETWEEN ? AND ?
                GROUP BY logged_date
                """, userId, start, end);

        Map<String, Double> result = new LinkedHashMap<>();
        for (Map<String, Object> row : rows) {
            result.put(row.get("logged_date").toString(), ((Number) row.get("total_kcal")).doubleValue());
        }
        return result;
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
     * 사용자가 그램을 직접 지정하는 행위이므로 인분수 환산은 거치지 않고 그대로 씀.
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
        String rawSearchName = target.get("searchName") != null ? (String) target.get("searchName") : foodName;
        String searchName = resolveSearchName(userId, foodName, rawSearchName);

        FoodNutritionLookupService.NutritionInfo info = nutritionLookupService.lookup(searchName, newAmountG);
        if (info == null) {
            throw new IllegalArgumentException("해당 음식을 다시 조회하지 못했어요.");
        }

        items.set(itemIndex, item(foodName, searchName, info, candidatesIfUnsure(searchName, info)));

        return recalculateAndSave(userId, mealId, items);
    }

    /**
     * food_items 배열 중 한 항목이 LIKE 폴백(FUZZY)으로만 매칭돼서 확실하지 않을 때, 사용자가 후보
     * 목록(candidates) 중 하나를 직접 선택하면 그 정확한 food_name으로 다시 계산하고, 같은 검색어에
     * 대한 이 선택을 기억해둠(UserFoodAliasService) - 다음에 같은 표현을 쓰면 자동으로 정확매칭됨.
     * 그램 수는 기존에 계산돼 있던 값을 그대로 유지함(그램을 같이 바꾸고 싶으면 updateMealItemAmount를 따로 호출).
     *
     * @param itemIndex        food_items 배열에서의 0부터 시작하는 인덱스
     * @param resolvedFoodName 사용자가 고른 후보 (food_nutrition_reference.food_name과 정확히 일치해야 함)
     */
    public MealItemUpdateResult resolveMealItemMatch(Long userId, Long mealId, int itemIndex, String resolvedFoodName) {
        if (resolvedFoodName == null || resolvedFoodName.isBlank()) {
            throw new IllegalArgumentException("선택한 음식명을 입력해주세요.");
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
        String previousSearchName = target.get("searchName") != null ? (String) target.get("searchName") : foodName;
        double currentAmountG = toDouble(target.get("amountG"));
        if (currentAmountG <= 0) {
            currentAmountG = 100; // 방어적 기본값 - 이 경로에 온 항목은 이미 저장돼 있었으므로 사실상 항상 양수임
        }

        // 사용자가 목록에서 고른 이름이라 food_name과 정확히 일치할 것 - EXACT_PRODUCT로 바로 매칭됨
        FoodNutritionLookupService.NutritionInfo info = nutritionLookupService.lookup(resolvedFoodName, currentAmountG);
        if (info == null) {
            throw new IllegalArgumentException("선택한 음식을 찾지 못했어요.");
        }

        items.set(itemIndex, item(foodName, resolvedFoodName, info, List.of()));

        // 이 사용자가 이 검색어를 다시 쓰면 다음부턴 후보 제시 없이 바로 이 매칭이 적용되도록 기억해둠
        foodAliasService.save(userId, previousSearchName, resolvedFoodName);

        return recalculateAndSave(userId, mealId, items);
    }

    private MealItemUpdateResult recalculateAndSave(Long userId, Long mealId, List<Map<String, Object>> items) {
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

    /** 회원 탈퇴 시 diet_meals는 JPA 엔티티가 아니라 CASCADE가 안 걸려있어서 직접 지워야 함 */
    public void deleteAllForUser(Long userId) {
        jdbcTemplate.update("DELETE FROM diet_meals WHERE user_id = ?", userId);
    }

    private String inferMealTypeByTime() {
        int hour = LocalTime.now().getHour();
        if (hour < 11) return "BREAKFAST";
        if (hour < 15) return "LUNCH";
        if (hour < 21) return "DINNER";
        return "SNACK";
    }
 
    /**
     * 이 사용자가 이 검색어에 대해 예전에 직접 골라둔 매칭이 있으면 그걸 우선 씀(별칭),
     * 없으면 기존 하드코딩 보정(normalizeSearchName)을 거친 이름을 씀.
     */
    private String resolveSearchName(Long userId, String foodName, String modelSearchName) {
        String normalized = normalizeSearchName(foodName, modelSearchName);
        return foodAliasService.findResolved(userId, normalized).orElse(normalized);
    }

    /** FUZZY 매칭이면 사용자에게 보여줄 후보 목록을 붙여줌 (확실한 매칭이면 빈 리스트) */
    private List<String> candidatesIfUnsure(String searchName, FoodNutritionLookupService.NutritionInfo info) {
        if (info.matchTier() != FoodNutritionLookupService.MatchTier.FUZZY) {
            return List.of();
        }
        return nutritionLookupService.suggestCandidates(searchName, 5);
    }

    /**
     * "밥"/"흰쌀밥"/"쌀밥"류는 searchName을 Qwen에게 직접 쓰게 하면 안 됨 - Ollama format:"json" 모드에서
     * 이 정확한 문자열("멥쌀밥")을 생성할 때 종종 깨진 문자열("miesamul" 등)을 뱉는 모델 버그가 있어서
     * 실제로 재현됨(온도 조절로도 해결 안 됨). foodName은 이 문제없이 항상 정상적으로 나오길래,
     * foodName을 기준으로 알려진 케이스만 코드에서 확정적으로 보정함.
     */
    private String normalizeSearchName(String foodName, String modelSearchName) {
        if (foodName == null) {
            return modelSearchName;
        }
        if (foodName.contains("찹쌀") && foodName.contains("밥")) {
            return "찹쌀밥";
        }
        if (foodName.equals("밥") || foodName.equals("흰쌀밥") || foodName.equals("쌀밥")
                || foodName.equals("백미밥") || foodName.equals("공깃밥")) {
            return "멥쌀밥";
        }
        return modelSearchName;
    }

    /** DB 매칭까지 성공한 항목만으로 메뉴명을 요약 (못 찾은 항목은 notFound로 따로 안내) */
    private String summarizeMenuNames(List<Map<String, Object>> foodItemsForJson) {
        return foodItemsForJson.stream()
                .map(m -> (String) m.get("foodName"))
                .reduce((a, b) -> a + ", " + b)
                .orElse("(인식된 음식 없음)");
    }

    private Map<String, Object> item(
            String foodName, String searchName, FoodNutritionLookupService.NutritionInfo info, List<String> candidates
    ) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("foodName", foodName);
        m.put("searchName", searchName);
        m.put("amountG", round1(info.amountG()));
        m.put("calories", round1(info.calories()));
        m.put("proteinG", round1(info.proteinG()));
        m.put("carbsG", round1(info.carbsG()));
        m.put("fatG", round1(info.fatG()));
        m.put("matchTier", info.matchTier().name());
        m.put("weightEstimated", info.weightEstimated());
        if (!candidates.isEmpty()) {
            m.put("candidates", candidates);
        }
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
                node.fields().forEachRemaining(entry -> m.put(entry.getKey(), toJavaValue(entry.getValue())));
                items.add(m);
            }
            return items;
        } catch (Exception e) {
            log.error("food_items JSON 파싱 실패. 원문: {}", json, e);
            throw new IllegalArgumentException("기존 기록을 읽는 중 문제가 생겼어요.");
        }
    }

    /** JSON 노드를 타입 보존해서 자바 값으로 변환 (숫자/불리언/배열/문자열) - candidates(배열), weightEstimated(불리언)도
     *  다시 저장할 때 깨지지 않게 하려면 전부 문자열로 뭉개면 안 됨 */
    private Object toJavaValue(JsonNode v) {
        if (v.isNumber()) return v.asDouble();
        if (v.isBoolean()) return v.asBoolean();
        if (v.isArray()) {
            List<String> list = new ArrayList<>();
            v.forEach(el -> list.add(el.asText()));
            return list;
        }
        return v.asText();
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
 
package com.kdt.wellmade.domain.nutrition;

 
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 식단관리 메뉴용 실제 API.
 *
 * 사용 흐름:
 *   1. POST /api/diet/meals - 오늘 먹은 거 기록
 *   2. GET  /api/diet/meals/today - 오늘 기록 목록
 *   3. GET  /api/diet/meals/today/total - 오늘 합계
 */
@RestController
@RequestMapping("/api/diet/meals")
public class DietMealController {

    private final MealLoggingService mealLoggingService;

    public DietMealController(MealLoggingService mealLoggingService) {
        this.mealLoggingService = mealLoggingService;
    }

    @PostMapping
    public MealLoggingService.MealLogResult logMeal(@AuthenticationPrincipal Long userId, @RequestBody LogMealRequest request) {
        return mealLoggingService.logMeal(userId, request.message(), request.mealType());
    }

    @GetMapping("/today")
    public List<Map<String, Object>> getTodayMeals(@AuthenticationPrincipal Long userId) {
        return mealLoggingService.getTodayMeals(userId);
    }

    @GetMapping("/today/total")
    public MealLoggingService.DailyTotal getTodayTotal(@AuthenticationPrincipal Long userId) {
        return mealLoggingService.getTodayTotal(userId);
    }

    public record LogMealRequest(String message, String mealType) {}
}
 
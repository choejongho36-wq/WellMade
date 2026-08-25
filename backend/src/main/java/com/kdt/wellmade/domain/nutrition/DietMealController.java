package com.kdt.wellmade.domain.nutrition;


import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.time.LocalDate;
import java.util.List;
import java.util.Map;

/**
 * 식단관리 메뉴용 실제 API.
 *
 * 사용 흐름:
 *   1. POST /api/diet/meals - 오늘 먹은 거 기록 (mealType 미지정 시 현재 시각으로 자동 추정)
 *   2. GET  /api/diet/meals/today?date=yyyy-MM-dd - 해당 날짜 기록 목록 (date 생략 시 오늘)
 *   3. GET  /api/diet/meals/today/total?date=yyyy-MM-dd - 해당 날짜 합계 (date 생략 시 오늘)
 *   4. DELETE /api/diet/meals/{id} - 기록 삭제 (본인 소유만)
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
    public List<Map<String, Object>> getMeals(
            @AuthenticationPrincipal Long userId,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate date
    ) {
        return mealLoggingService.getMealsForDate(userId, date != null ? date : LocalDate.now());
    }

    @GetMapping("/today/total")
    public MealLoggingService.DailyTotal getTotal(
            @AuthenticationPrincipal Long userId,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate date
    ) {
        return mealLoggingService.getTotalForDate(userId, date != null ? date : LocalDate.now());
    }

    @PutMapping("/{id}")
    public void updateMeal(
            @AuthenticationPrincipal Long userId,
            @PathVariable Long id,
            @RequestBody UpdateMealRequest request
    ) {
        mealLoggingService.updateMeal(userId, id, request.mealType(), request.menuName(), request.kcal());
    }

    @DeleteMapping("/{id}")
    public void deleteMeal(@AuthenticationPrincipal Long userId, @PathVariable Long id) {
        mealLoggingService.deleteMeal(userId, id);
    }

    public record LogMealRequest(String message, String mealType) {}
    public record UpdateMealRequest(String mealType, String menuName, double kcal) {}
}
 
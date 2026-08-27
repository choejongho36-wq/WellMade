package com.kdt.wellmade.domain.nutrition;


import com.kdt.wellmade.domain.inbody.InbodyRecord;
import com.kdt.wellmade.domain.inbody.InbodyService;
import com.kdt.wellmade.domain.mapage.UserProfile;
import com.kdt.wellmade.domain.mapage.UserProfileService;
import com.kdt.wellmade.domain.user.User;
import com.kdt.wellmade.domain.user.UserService;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.ResponseEntity;
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
 *   2. GET  /api/diet/meals/today?date=yyyy-MM-dd - 해당 날짜 기록 목록 (date 생략 시 오늘, food_items에 항목별 그램/칼로리 포함)
 *   3. GET  /api/diet/meals/today/total?date=yyyy-MM-dd - 해당 날짜 합계 (date 생략 시 오늘)
 *   4. GET  /api/diet/meals/month?year=&month= - 해당 월의 날짜별 칼로리 합계 (달력 칸 표시용)
 *   5. PUT  /api/diet/meals/{id} - 끼니 종류/메뉴명/칼로리 직접 수정 (본인 소유만)
 *   6. PATCH /api/diet/meals/{id}/items/{itemIndex} - food_items 배열의 특정 항목 그램 수만 수정
 *      (해당 음식을 새 그램 수로 다시 조회해서 끼니 전체 합계까지 재계산함, 본인 소유만)
 *   7. DELETE /api/diet/meals/{id} - 기록 삭제 (본인 소유만)
 *   8. GET  /api/diet/meals/target - 하루 목표 섭취량 (직접 수정한 값이 있으면 그 값, 없으면 목표+인바디 기반 추천값. 계산 불가하면 204)
 *   9. PUT  /api/diet/meals/target - 목표 섭취량 직접 수정
 *   10. DELETE /api/diet/meals/target - 직접 수정한 목표를 지우고 추천값으로 되돌림
 */
@RestController
@RequestMapping("/api/diet/meals")
public class DietMealController {

    private final MealLoggingService mealLoggingService;
    private final UserService userService;
    private final UserProfileService userProfileService;
    private final InbodyService inbodyService;
    private final NutrientTargetCalculator nutrientTargetCalculator;

    public DietMealController(
            MealLoggingService mealLoggingService,
            UserService userService,
            UserProfileService userProfileService,
            InbodyService inbodyService,
            NutrientTargetCalculator nutrientTargetCalculator
    ) {
        this.mealLoggingService = mealLoggingService;
        this.userService = userService;
        this.userProfileService = userProfileService;
        this.inbodyService = inbodyService;
        this.nutrientTargetCalculator = nutrientTargetCalculator;
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

    @GetMapping("/month")
    public Map<String, Double> getMonthCalories(
            @AuthenticationPrincipal Long userId,
            @RequestParam int year,
            @RequestParam int month
    ) {
        return mealLoggingService.getDailyCaloriesForMonth(userId, year, month);
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

    @PatchMapping("/{id}/items/{itemIndex}")
    public MealLoggingService.MealItemUpdateResult updateMealItemAmount(
            @AuthenticationPrincipal Long userId,
            @PathVariable Long id,
            @PathVariable int itemIndex,
            @RequestBody UpdateMealItemRequest request
    ) {
        return mealLoggingService.updateMealItemAmount(userId, id, itemIndex, request.amountG());
    }

    @DeleteMapping("/{id}")
    public void deleteMeal(@AuthenticationPrincipal Long userId, @PathVariable Long id) {
        mealLoggingService.deleteMeal(userId, id);
    }

    /**
     * 목표 섭취량. 사용자가 직접 수정해둔 값이 있으면 그걸(custom=true), 없으면 목표(Goal)+최근 인바디로
     * 계산한 추천값을(custom=false) 돌려줌. 목표/인바디가 아직 없어서 추천값도 계산 못 하면 204(본문 없음)
     */
    @GetMapping("/target")
    public ResponseEntity<TargetResponse> getTarget(@AuthenticationPrincipal Long userId) {
        User user = userService.getUser(userId);
        UserProfile profile = getProfileOrNull(user);
        if (profile == null || profile.getGoal() == null) {
            return ResponseEntity.noContent().build();
        }

        if (profile.getTargetKcal() != null) {
            return ResponseEntity.ok(new TargetResponse(
                    profile.getTargetKcal(), profile.getTargetProteinG(),
                    profile.getTargetCarbsG(), profile.getTargetFatG(), true
            ));
        }

        InbodyRecord inbody = inbodyService.getLatest(user).orElse(null);
        if (inbody == null || inbody.getWeightKg() == null) {
            return ResponseEntity.noContent().build();
        }

        NutrientTarget recommended = nutrientTargetCalculator.calculate(inbody, profile.getGoal());
        return ResponseEntity.ok(new TargetResponse(
                recommended.kcal(), recommended.proteinG(), recommended.carbsG(), recommended.fatG(), false
        ));
    }

    /** 목표 섭취량을 직접 지정 (추천값 대신 사용) */
    @PutMapping("/target")
    public void updateTarget(@AuthenticationPrincipal Long userId, @RequestBody UpdateTargetRequest request) {
        User user = userService.getUser(userId);
        userProfileService.updateTarget(user, request.kcal(), request.proteinG(), request.carbsG(), request.fatG());
    }

    /** 직접 지정한 목표를 지우고 추천값 자동계산으로 되돌림 */
    @DeleteMapping("/target")
    public void resetTarget(@AuthenticationPrincipal Long userId) {
        User user = userService.getUser(userId);
        userProfileService.updateTarget(user, null, null, null, null);
    }

    private UserProfile getProfileOrNull(User user) {
        try {
            return userProfileService.getProfile(user);
        } catch (IllegalArgumentException e) {
            return null;
        }
    }

    public record LogMealRequest(String message, String mealType) {}
    public record UpdateMealRequest(String mealType, String menuName, double kcal) {}
    public record UpdateMealItemRequest(double amountG) {}
    public record TargetResponse(double kcal, double proteinG, double carbsG, double fatG, boolean custom) {}
    public record UpdateTargetRequest(double kcal, double proteinG, double carbsG, double fatG) {}
}
 
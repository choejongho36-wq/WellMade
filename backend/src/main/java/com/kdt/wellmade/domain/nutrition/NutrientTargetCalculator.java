package com.kdt.wellmade.domain.nutrition;

import com.kdt.wellmade.domain.inbody.InbodyRecord;
import com.kdt.wellmade.domain.mapage.Goal;
import org.springframework.stereotype.Component;

/**
 * 인바디 수치 + 목표(Goal)로 하루 목표 칼로리/단백질/탄수화물/지방을 계산하는 순수 계산 로직.
 * ChatService(챗봇 조언/도구호출)와 DietMealController(칼로리 모달의 목표 대비 비교)가 이 계산을 공유해서 씀.
 */
@Component
public class NutrientTargetCalculator {

    /** ponytail: 활동계수 1.375(가벼운 활동) 고정값, 기초대사량 없으면 체중×24로 대략 추정 - 활동량 입력 받으면 그걸로 교체 */
    public NutrientTarget calculate(InbodyRecord inbody, Goal goal) {
        double weight = inbody.getWeightKg();
        double bmr = inbody.getBasalMetabolicRateKcal() != null ? inbody.getBasalMetabolicRateKcal() : weight * 24;
        double tdee = bmr * 1.375;

        double targetKcal = switch (goal) {
            case LOSE -> tdee * 0.85;
            case GAIN -> tdee * 1.15;
            case MAINTAIN -> tdee;
        };
        double proteinPerKg = switch (goal) {
            case LOSE -> 1.8;
            case GAIN -> 2.0;
            case MAINTAIN -> 1.4;
        };
        double targetProtein = weight * proteinPerKg;
        double targetFat = targetKcal * 0.25 / 9;
        double targetCarbs = Math.max(0, (targetKcal - targetProtein * 4 - targetFat * 9) / 4);

        return new NutrientTarget(targetKcal, targetProtein, targetCarbs, targetFat);
    }
}

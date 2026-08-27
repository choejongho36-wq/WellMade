package com.kdt.wellmade.domain.nutrition;

import java.time.LocalDate;

import com.kdt.wellmade.domain.inbody.InbodyRecord;
import com.kdt.wellmade.domain.mapage.Gender;
import com.kdt.wellmade.domain.mapage.Goal;
import com.kdt.wellmade.domain.mapage.UserProfile;

import org.springframework.stereotype.Component;

/**
 * 인바디 수치 + 프로필(목표/성별/키/나이)로 하루 목표 칼로리/단백질/탄수화물/지방을 계산하는 순수 계산 로직.
 * ChatService(챗봇 조언/도구호출)와 DietMealController(칼로리 모달의 목표 대비 비교)가 이 계산을 공유해서 씀.
 */
@Component
public class NutrientTargetCalculator {

    /** ponytail: 활동계수 1.375(가벼운 활동) 고정값 - 활동량 입력을 받게 되면 그걸로 교체 */
    private static final double ACTIVITY_FACTOR = 1.375;

    public NutrientTarget calculate(InbodyRecord inbody, UserProfile profile) {
        double weight = inbody.getWeightKg();
        double tdee = basalMetabolicRate(inbody, profile, weight) * ACTIVITY_FACTOR;
        Goal goal = profile.getGoal();

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

    /**
     * 우선순위: 인바디 실측값 > Mifflin-St Jeor(성별·키·나이 필요) > 체중×24.
     * 마지막 fallback은 성별을 무시해서 여성 기준 200~300kcal 과대추정이 나므로,
     * 프론트에서 성별/키/출생연도 입력을 안내해 두 번째 단계로 올라가게 하는 게 정상 경로임.
     */
    private double basalMetabolicRate(InbodyRecord inbody, UserProfile profile, double weight) {
        if (inbody.getBasalMetabolicRateKcal() != null) {
            return inbody.getBasalMetabolicRateKcal();
        }

        Gender gender = profile.getGender();
        Double heightCm = profile.getHeightCm();
        Integer birthYear = profile.getBirthYear();
        if (gender == null || heightCm == null || birthYear == null) {
            return weight * 24;
        }

        int age = Math.max(1, LocalDate.now().getYear() - birthYear);
        double base = 10 * weight + 6.25 * heightCm - 5 * age;
        return gender == Gender.MALE ? base + 5 : base - 161;
    }
}

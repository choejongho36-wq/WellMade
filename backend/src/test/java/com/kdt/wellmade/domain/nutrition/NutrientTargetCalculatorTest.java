package com.kdt.wellmade.domain.nutrition;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.LocalDate;

import org.junit.jupiter.api.Test;

import com.kdt.wellmade.domain.inbody.InbodyRecord;
import com.kdt.wellmade.domain.mapage.Gender;
import com.kdt.wellmade.domain.mapage.Goal;
import com.kdt.wellmade.domain.mapage.UserProfile;

class NutrientTargetCalculatorTest {

    private final NutrientTargetCalculator calculator = new NutrientTargetCalculator();

    private UserProfile profile(Gender gender, Double heightCm, Integer birthYear) {
        UserProfile profile = UserProfile.builder().goal(Goal.MAINTAIN).build();
        profile.updateBody(gender, heightCm, birthYear);
        return profile;
    }

    private InbodyRecord inbody(Integer bmr) {
        return InbodyRecord.builder().weightKg(70.0).basalMetabolicRateKcal(bmr).build();
    }

    /** 이 케이스를 못 잡으면 성별 반영이 통째로 빠진 것 */
    @Test
    void sameBodyDifferentGenderGivesDifferentTarget() {
        int birthYear = LocalDate.now().getYear() - 30;
        double male = calculator.calculate(inbody(null), profile(Gender.MALE, 175.0, birthYear)).kcal();
        double female = calculator.calculate(inbody(null), profile(Gender.FEMALE, 175.0, birthYear)).kcal();

        // Mifflin-St Jeor 상수 차이(+5 vs -161)에 활동계수 1.375가 곱해진 만큼
        assertEquals(166 * 1.375, male - female, 0.01);
    }

    @Test
    void tallerUserGetsHigherTarget() {
        int birthYear = LocalDate.now().getYear() - 30;
        double tall = calculator.calculate(inbody(null), profile(Gender.MALE, 185.0, birthYear)).kcal();
        double shortUser = calculator.calculate(inbody(null), profile(Gender.MALE, 165.0, birthYear)).kcal();

        assertTrue(tall > shortUser, "키가 크면 기초대사량이 높아야 함");
    }

    /** 인바디 실측 기초대사량이 있으면 추정 공식보다 그걸 우선 */
    @Test
    void measuredBmrWinsOverEstimate() {
        UserProfile p = profile(Gender.FEMALE, 160.0, 1990);

        assertEquals(1500 * 1.375, calculator.calculate(inbody(1500), p).kcal(), 0.01);
    }

    /** 성별/키/출생연도가 비어 있으면 기존 체중×24 추정으로 떨어짐 */
    @Test
    void fallsBackToWeightEstimateWhenBodyInfoMissing() {
        UserProfile p = profile(null, null, null);

        assertEquals(70.0 * 24 * 1.375, calculator.calculate(inbody(null), p).kcal(), 0.01);
    }
}

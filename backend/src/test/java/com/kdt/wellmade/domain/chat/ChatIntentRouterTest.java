package com.kdt.wellmade.domain.chat;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.LocalDate;
import java.util.List;
import java.util.Optional;

import org.junit.jupiter.api.Test;

/**
 * 서버가 도구를 정하는 라우터. 모델이 도구를 "고르는" 단계가 확률적으로 실패해서(예고만 쓰고 끝냄,
 * 안 부르고 지어냄 - 전부 실측) 흔한 의도는 여기서 결정한다. 잘못 라우팅하면 엉뚱한 데이터로
 * 답하므로, 뻔한 문장은 반드시 잡고 애매한 문장은 반드시 넘겨야 한다.
 */
class ChatIntentRouterTest {

    private static final LocalDate TODAY = LocalDate.of(2026, 9, 10);

    private static String toolOf(String message) {
        return ChatIntentRouter.route(message, null, TODAY)
                .map(r -> r.calls().get(0).function().name())
                .orElse(null);
    }

    private static Object argOf(String message, String key) {
        return ChatIntentRouter.route(message, null, TODAY)
                .map(r -> r.calls().get(0).function().arguments().get(key))
                .orElse(null);
    }

    // ---- 스크린샷에서 실제로 실패한 문장들 ----

    @Test
    void whatShouldIEatIsMealRecommendation() {
        // "오늘 저녁 뭐먹지"에 모델이 "확인해보겠습니다"만 쓰고 끝냈다. 서버가 도구를 정한다.
        Optional<ChatIntentRouter.Route> route = ChatIntentRouter.route("오늘 저녁 뭐먹지", null, TODAY);

        assertTrue(route.isPresent());
        List<String> tools = route.get().calls().stream().map(c -> c.function().name()).toList();
        assertEquals(List.of("get_daily_total", "calculate_nutrient_target"), tools);
        // 추천은 기록이 없어도 답할 수 있으니 모델이 문장을 만든다
        assertFalse(route.get().answerDirectlyWhenEmpty());
    }

    @Test
    void terseWhatToEatStillRoutes() {
        assertEquals("get_daily_total", toolOf("뭐먹냐고"));
    }

    @Test
    void dumbbellLowerBodyAnswerRoutesToRecommendation() {
        // 되묻기에 "덤벨 하체운동"이라 답했는데 모델이 영어로 지어냈다
        Optional<ChatIntentRouter.Route> route =
                ChatIntentRouter.route("덤벨 하체운동", ChatIntentRouter.FOLLOW_UP_EXERCISE_BUTTON, TODAY);

        assertTrue(route.isPresent());
        assertEquals("recommend_exercises", route.get().calls().get(0).function().name());
        // 부위/장비 파싱은 AI 서버 몫이라 문장을 그대로 넘긴다
        assertEquals("덤벨 하체운동", route.get().calls().get(0).function().arguments().get("body_part"));
        assertEquals("덤벨 하체운동", route.get().calls().get(0).function().arguments().get("equipment"));
    }

    @Test
    void serverDrivenFollowUpAlsoRoutesToRecommendation() {
        Optional<ChatIntentRouter.Route> route =
                ChatIntentRouter.route("상체", ChatIntentRouter.FOLLOW_UP_EXERCISE_SERVER, TODAY);

        assertEquals("recommend_exercises", route.orElseThrow().calls().get(0).function().name());
    }

    // ---- 식사 기록 ----

    @Test
    void pastMealsRouteToMealsForDate() {
        assertEquals("get_meals_for_date", toolOf("오늘 뭐 먹었지?"));
        assertEquals("get_meals_for_date", toolOf("어제 먹은 거 보여줘"));
        assertEquals("2026-09-09", argOf("어제 먹은 거 보여줘", "date"));
        assertEquals("2026-09-08", argOf("그저께 뭐 먹었더라", "date"));
    }

    @Test
    void calorieQuestionsRouteToDailyTotal() {
        assertEquals("get_daily_total", toolOf("어제 총 몇 칼로리 먹었어?"));
        assertEquals("get_daily_total", toolOf("오늘 섭취량 얼마야"));
        assertEquals("2026-09-09", argOf("어제 총 몇 칼로리 먹었어?", "date"));
    }

    @Test
    void targetQuestionsRouteToNutrientTarget() {
        assertEquals("calculate_nutrient_target", toolOf("내 목표 섭취량 얼마야?"));
        assertEquals("calculate_nutrient_target", toolOf("하루에 얼마나 먹어야 해?"));
    }

    @Test
    void vaguePeriodsAreLeftToTheModel() {
        // "이번 주"는 날짜 하나로 못 만든다 - 모델이 판단하게 둔다
        assertEquals(null, toolOf("이번 주에 뭐 먹었지?"));
        assertEquals(null, toolOf("최근에 칼로리 얼마나 먹었어?"));
    }

    // ---- 운동 ----

    @Test
    void exerciseRecommendationWithBodyPartRoutes() {
        assertEquals("recommend_exercises", toolOf("하체 운동 추천해줘"));
        assertEquals("recommend_exercises", toolOf("어깨 운동 뭐 하면 좋아?"));
        assertEquals("recommend_exercises", toolOf("복근 운동 3개만 알려줘"));
    }

    @Test
    void howToDoAnExerciseRoutesToDetail() {
        assertEquals("get_exercise_detail", toolOf("플랭크는 어떻게 하는 거야?"));
        assertEquals("get_exercise_detail", toolOf("덤벨 런지 자세 알려줘"));
        // 이름 추출은 AI 서버가 문장에서 직접 한다
        assertEquals("플랭크는 어떻게 하는 거야?", argOf("플랭크는 어떻게 하는 거야?", "name"));
    }

    @Test
    void howToQuestionsAboutFoodAreNotExerciseDetail() {
        assertEquals(null, toolOf("다이어트 식단은 어떻게 해?"));
    }

    // ---- 인바디 / 또래 ----

    @Test
    void weightTrendRoutesToInbodyHistory() {
        assertEquals("get_inbody_history", toolOf("요즘 체중 변화 어때?"));
        assertEquals("get_inbody_history", toolOf("몸무게 늘었어?"));
    }

    @Test
    void peerComparisonsRouteBeforeMealLookup() {
        // "먹었"이 들어 있어도 "또래"가 붙으면 비교 도구다
        assertEquals("get_nutrition_peer_comparison", toolOf("나 또래보다 많이 먹었나?"));
        assertEquals("get_bmi_peer_comparison", toolOf("내 BMI 또래랑 비교하면 어때?"));
    }

    // ---- 넘겨야 하는 것 ----

    @Test
    void greetingsAndChitChatAreNotRouted() {
        assertEquals(null, toolOf("안녕"));
        assertEquals(null, toolOf("고마워"));
        assertEquals(null, toolOf("너 누구야?"));
    }

    @Test
    void longMessagesAreLeftToTheModel() {
        String longMessage = "어제 저녁에 회식이 있어서 삼겹살을 많이 먹었는데 오늘은 뭘 먹어야 어제 먹은 걸 만회할 수 있을지 "
                + "그리고 운동은 뭘 하면 좋을지 같이 알려줘";
        assertEquals(null, toolOf(longMessage));
    }
}

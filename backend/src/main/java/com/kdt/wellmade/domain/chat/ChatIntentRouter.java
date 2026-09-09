package com.kdt.wellmade.domain.chat;

import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * 사용자 문장에서 "어떤 도구를 불러야 하는지"가 명백한 경우를 모델보다 먼저 서버가 결정한다.
 *
 * 왜 모델에게 맡기지 않나: 메뉴 버튼 경로(ChatService.menuReply)를 만들 때 이미 확인된 사실인데,
 * 7B 모델이 도구를 "고르는" 단계는 확률적으로 실패한다 - 툴콜을 텍스트로 흘리거나, "확인해보겠습니다"
 * 예고만 쓰고 끝내거나, 아예 안 부르고 지어낸다(전부 실측). 온도를 0.2까지 내려도 남는다.
 * 버튼은 서버가 도구를 직접 실행하도록 바꿔서 그 단계를 없앴는데, 사용자가 직접 친 문장은
 * 여전히 모델이 고르고 있었다. "오늘 뭐 먹었지?"가 버튼으로 오면 확실하고 타자로 오면 확률적이라는
 * 건 사용자 입장에서 설명이 안 된다.
 *
 * 그래서 문장이 뻔한 의도면 여기서 도구를 정한다. 못 정하면 빈 값을 돌려주고 모델이 고른다 -
 * 이 라우터는 모델을 대체하는 게 아니라 모델이 실패하는 흔한 경우를 앞에서 받아내는 안전망이다.
 *
 * 규칙은 전부 부분 문자열 검사다. 정규식이나 형태소 분석을 안 쓰는 이유: 여기 들어오는 문장은
 * 짧은 대화체라 키워드로 충분하고, 틀렸을 때의 비용이 "관련 있는 실제 데이터를 근거로 답하는 것"
 * 이라 지어내는 것보다 항상 낫다. 다만 긴 문장은 의도가 여럿일 수 있어 모델에게 넘긴다.
 */
final class ChatIntentRouter {

    /**
     * 라우팅 결과.
     *
     * @param calls 서버가 실행할 도구 호출(모델이 부른 것과 같은 형태로 컨텍스트에 넣는다)
     * @param answerDirectlyWhenEmpty 도구 결과가 "데이터 없음"이면 모델을 부르지 않고 그 문장을
     *        그대로 답으로 쓸지. 기록 조회는 true - 없는 기록을 모델이 채울 여지를 없앤다.
     *        식사 추천처럼 데이터가 없어도 답할 수 있는 의도는 false.
     */
    record Route(List<OllamaMessage.ToolCall> calls, boolean answerDirectlyWhenEmpty) {
        static Route of(String toolName, Map<String, Object> arguments, boolean answerDirectlyWhenEmpty) {
            return new Route(List.of(call(toolName, arguments)), answerDirectlyWhenEmpty);
        }
    }

    /** 이보다 길면 의도가 여럿 섞였을 수 있으니 모델에게 넘긴다. 라우팅 대상 문장은 대개 20자 안쪽이다 */
    private static final int MAX_ROUTED_LENGTH = 60;

    /** 되묻기("어느 부위?")에 대한 답. 버튼에서 온 것이든 서버가 되물은 것이든 부위 답이다 */
    static final String FOLLOW_UP_EXERCISE_BUTTON = "exercise-recommend";
    static final String FOLLOW_UP_EXERCISE_SERVER = "exercise-body-part";

    private ChatIntentRouter() {
    }

    static Optional<Route> route(String message, String followUpId, LocalDate today) {
        if (message == null) {
            return Optional.empty();
        }
        String text = message.trim();

        // 되묻기에 대한 답은 길이와 무관하게 무조건 운동 추천이다 - 사용자가 부위를 말하려고 친 문장이다
        if (FOLLOW_UP_EXERCISE_BUTTON.equals(followUpId) || FOLLOW_UP_EXERCISE_SERVER.equals(followUpId)) {
            return Optional.of(exerciseRecommend(text));
        }
        if (text.isEmpty() || text.length() > MAX_ROUTED_LENGTH) {
            return Optional.empty();
        }

        boolean peer = containsAny(text, "또래", "평균", "남들");
        boolean food = containsAny(text, "먹", "식단", "식사", "칼로리", "섭취", "메뉴", "끼니");
        // 식사와 운동을 한 문장에 같이 물으면 도구 하나로는 답이 안 된다 - 모델이 둘 다 부르게 둔다
        if (food && text.contains("운동")) {
            return Optional.empty();
        }
        boolean pastFood = containsAny(text, "먹었", "먹은");
        boolean askingHow = containsAny(text,
                "어떻게 해", "어떻게 하", "하는 방법", "하는 법", "방법 알려", "방법 좀", "자세 알려", "자세 설명",
                "자세 좀", "설명해", "동작 알려");
        // 날짜가 특정되지 않는 기간 표현은 도구 인자로 못 만든다 - 모델이 판단하게 둔다
        boolean vaguePeriod = containsAny(text, "이번 주", "이번주", "지난주", "지난 주", "요일", "이번 달", "지난달", "최근", "요즘");

        // --- 또래 비교: "또래"가 붙으면 먹었든 체중이든 비교 도구다 (먹었 검사보다 먼저) ---
        if (peer) {
            if (food) {
                return Optional.of(Route.of("get_nutrition_peer_comparison",
                        Map.of("date", dateOf(text, today).toString()), true));
            }
            if (containsAny(text, "bmi", "BMI", "체중", "몸무게", "비만", "뚱뚱", "말랐")) {
                return Optional.of(Route.of("get_bmi_peer_comparison", Map.of(), true));
            }
            return Optional.empty();
        }

        // --- 운동 설명: "플랭크는 어떻게 해?" - 이름 추출은 AI 서버가 문장에서 직접 한다 ---
        if (askingHow && !food && !text.contains("추천")) {
            return Optional.of(Route.of("get_exercise_detail", Map.of("name", text), true));
        }

        // --- 운동 추천: 부위/장비 파싱은 AI 서버 몫이라 문장을 그대로 넘긴다 ---
        //
        // 예전엔 요청 동사("추천", "알려")가 붙은 문장만 잡았는데, 되묻기에 답한 뒤 조건만 더
        // 던지는 흐름("맨몸운동", "바벨 운동")이 여기서 새어나가 모델이 그대로 지어냈다
        // (실측: 데이터에 없는 "퀀텀 레그 Curl", "레그_PRESS" + 지어낸 주의사항).
        // "운동"이 들어간 짧은 문장은 이 앱에서 사실상 추천 요청이므로 동사 없이도 잡는다.
        // 부위를 못 읽으면 AI 서버가 후보 0건 + 안내문을 돌려주고 되묻기를 건다 - 지어내는
        // 것보다 되묻는 편이 낫다. 다만 지나간 일을 말하는 문장("어제 운동했어")은 뺀다.
        if (text.contains("운동") && !food && !containsAny(text, "했", "한다", "할게", "하는 중", "중이")) {
            return Optional.of(exerciseRecommend(text));
        }

        // --- 목표 섭취량 ---
        if (text.contains("목표") && containsAny(text, "섭취", "칼로리", "먹어야", "단백질")) {
            return Optional.of(Route.of("calculate_nutrient_target", Map.of(), true));
        }
        if (containsAny(text, "먹어야", "먹어야지", "먹어야 해", "먹어야 하")) {
            // "하루에 얼마나 먹어야 해?" - 목표 섭취량 질문이다
            return Optional.of(Route.of("calculate_nutrient_target", Map.of(), true));
        }

        // --- 식사 추천: "오늘 저녁 뭐 먹지" - 오늘 섭취량과 목표를 근거로 모델이 제안한다 ---
        if (text.contains("먹") && !pastFood && containsAny(text, "뭐", "추천", "메뉴", "어떤")) {
            return Optional.of(new Route(List.of(
                    call("get_daily_total", Map.of("date", today.toString())),
                    call("calculate_nutrient_target", Map.of())
            ), false));
        }

        // --- 체중 추세: 날짜 인자가 없어서 "요즘"이 붙어도 된다 (기간 가드보다 먼저) ---
        if (containsAny(text, "체중", "몸무게", "인바디")
                && containsAny(text, "변화", "추세", "어때", "요즘", "늘었", "줄었", "빠지", "쪘", "빠졌", "기록")) {
            return Optional.of(Route.of("get_inbody_history", Map.of("limit", 5), true));
        }

        if (vaguePeriod) {
            return Optional.empty();
        }

        // --- 섭취량 합계: 칼로리/섭취량을 묻는 건 목록이 아니라 합계다 ---
        if (containsAny(text, "칼로리", "섭취량", "얼마나 먹", "몇 칼", "총")
                && (pastFood || containsAny(text, "오늘", "어제", "그제", "그저께", "섭취"))) {
            return Optional.of(Route.of("get_daily_total", Map.of("date", dateOf(text, today).toString()), true));
        }

        // --- 식사 기록 조회: "식단"만으로는 넓다("다이어트 식단은 어떻게 해?") - 과거형이거나 날짜가 붙어야 한다 ---
        boolean datedMeal = containsAny(text, "식단", "식사") && containsAny(text, "오늘", "어제", "그제", "그저께");
        if ((pastFood || datedMeal || containsAny(text, "식사 기록", "먹은 거", "먹은거")) && !text.contains("추천")) {
            return Optional.of(Route.of("get_meals_for_date", Map.of("date", dateOf(text, today).toString()), true));
        }

        return Optional.empty();
    }

    private static Route exerciseRecommend(String text) {
        // 부위와 장비를 나눠 뽑지 않고 둘 다 문장을 준다 - AI 서버의 부위 사전과 장비 사전이 각자
        // 자기 것만 골라 읽는다("덤벨 하체운동" -> 하체 + 덤벨). 사전은 그쪽 한 곳에만 둔다.
        return Route.of("recommend_exercises", Map.of("body_part", text, "equipment", text), true);
    }

    /** "어제", "그제/그저께"만 본다. 그 밖의 표현은 오늘 - 라우팅 전에 vaguePeriod로 걸러진다 */
    static LocalDate dateOf(String text, LocalDate today) {
        if (containsAny(text, "그제", "그저께")) {
            return today.minusDays(2);
        }
        if (text.contains("어제")) {
            return today.minusDays(1);
        }
        return today;
    }

    private static boolean containsAny(String text, String... words) {
        for (String word : words) {
            if (text.contains(word)) {
                return true;
            }
        }
        return false;
    }

    private static OllamaMessage.ToolCall call(String name, Map<String, Object> arguments) {
        return new OllamaMessage.ToolCall("route-" + name, new OllamaMessage.FunctionCall(name, arguments));
    }
}

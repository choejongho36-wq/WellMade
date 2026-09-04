package com.kdt.wellmade.domain.chat;

import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

import com.fasterxml.jackson.databind.ObjectMapper;

/**
 * 챗봇 회귀 평가 하네스 - 실제 Ollama를 띄워놓고 돌린다.
 *
 * 주석에 "6회 중 0회", "12회 중 1회" 같은 실측이 흩어져 있는데, 그건 사람이 손으로 세어본
 * 값이라 프롬프트나 모델을 바꿀 때마다 다시 셀 수가 없다. 같은 질문 세트를 자동으로 던지고
 * 세 가지를 기계적으로 채점해서, 바꾼 뒤에 나빠졌는지 바로 보이게 한다.
 *
 *   (a) 도구를 불렀나          - 안 부르면 검증 없는 답이 그대로 나간다
 *   (b) 추천이 후보 안에 있나  - 후보 밖 운동을 말하면 지어낸 것이다
 *   (c) 한국어로만 답했나      - Qwen이 중국어/영어로 새는 턴이 실제로 나온다
 *
 * 실행 (Ollama가 떠 있어야 함):
 *
 *   CHAT_EVAL=1 CHAT_EVAL_MODEL=qwen2.5:7b ./gradlew test --tests '*ChatExerciseEvalTest'
 *
 * 환경변수가 없으면 통째로 건너뛴다 - 일반 빌드가 외부 서버에 의존하면 안 되기 때문이다.
 * 실제 프롬프트({@link ChatService#SYSTEM_PROMPT})와 실제 도구 정의({@link ChatToolExecutor#TOOLS})를
 * 그대로 쓰므로, 프롬프트를 고치면 이 평가도 자동으로 새 프롬프트를 본다(따로 복사해두면 어긋난다).
 */
@EnabledIfEnvironmentVariable(named = "CHAT_EVAL", matches = "1")
class ChatExerciseEvalTest {

    /** 이 비율 아래로 떨어지면 회귀로 본다. 모델이 확률적이라 100%를 요구하지는 않는다. */
    private static final double PASS_RATE = 0.8;

    /**
     * 평가용 고정 후보. 실제 AI 서버를 띄우지 않고도 (b)를 채점하려면 후보가 고정돼야 한다 -
     * 모델이 이 넷 밖의 운동을 말하면 지어낸 것이다.
     */
    private static final List<String> FIXED_CANDIDATES =
            List.of("덤벨 고블릿 스쿼트", "덤벨 런지", "밴드 스쿼트", "덤벨 스텝업");

    private static final String FIXED_TOOL_RESULT = """
            {"body_part_ko":"하체","goal":"근육량 증가","plan":"3세트 x 8~12회 · 세트 사이 60~90초 휴식",
             "cautions":["무릎이 발끝보다 과하게 나가지 않게 하고, 허리를 굽히지 마세요."],
             "candidates":[
              {"name":"덤벨 고블릿 스쿼트","difficulty":"초급","sets_reps":"3세트 x 8~12회",
               "instructions_ko":"덤벨을 가슴 앞에 세워 들고 발을 어깨너비로 벌립니다. 허리를 편 채로 앉았다 일어섭니다."},
              {"name":"덤벨 런지","difficulty":"초급","sets_reps":"3세트 x 8~12회",
               "instructions_ko":"양손에 덤벨을 들고 한 발을 앞으로 내딛어 무릎을 굽혔다가 돌아옵니다."},
              {"name":"밴드 스쿼트","difficulty":"초급","sets_reps":"3세트 x 8~12회",
               "instructions_ko":"밴드를 발로 밟고 어깨에 걸친 뒤 앉았다 일어섭니다."},
              {"name":"덤벨 스텝업","difficulty":"초급","sets_reps":"3세트 x 8~12회",
               "instructions_ko":"덤벨을 들고 박스에 한 발씩 올라섰다 내려옵니다."}]}""";

    /**
     * 영어·한자가 섞이지 않았는지 볼 때 예외로 둘 표현. 단위나 약어는 한국어 답변에도 정상적으로 나온다.
     */
    private static final Set<String> ALLOWED_ASCII_WORDS = Set.of(
            "kcal", "kg", "cm", "bmi", "ai", "set", "sets", "reps", "ok", "inbody");

    /**
     * @param prompt      사용자 발화
     * @param expectTool  이 턴에 반드시 불러야 하는 도구 (없으면 null - 도구 없이 답해야 하는 턴)
     * @param checkPicks  추천이 후보 안에 있는지까지 볼 것인지
     */
    private record EvalCase(String prompt, String expectTool, boolean checkPicks) {}

    private static final List<EvalCase> CASES = List.of(
            // --- 운동 추천: 도구를 부르고, 후보 안에서만 골라야 한다 ---
            new EvalCase("하체 운동 추천해줘", "recommend_exercises", true),
            new EvalCase("집에서 할 수 있는 등 운동 알려줘", "recommend_exercises", true),
            new EvalCase("어깨 운동 뭐 하면 좋아?", "recommend_exercises", true),
            new EvalCase("덤벨로 할 수 있는 가슴 운동 추천", "recommend_exercises", true),
            new EvalCase("복근 운동 3개만 알려줘", "recommend_exercises", true),
            new EvalCase("운동을 추천받고 싶어요. 원하는 조건: 하체, 맨몸", "recommend_exercises", true),
            new EvalCase("유산소 뭐 할까?", "recommend_exercises", true),
            new EvalCase("팔 운동이랑 세트 수까지 알려줘", "recommend_exercises", true),

            // --- 운동 설명: 설명을 지어내지 말고 도구를 불러야 한다 ---
            new EvalCase("플랭크는 어떻게 하는 거야?", "get_exercise_detail", false),
            new EvalCase("버피 하는 방법 알려줘", "get_exercise_detail", false),
            new EvalCase("데드리프트 자세 설명해줘", "get_exercise_detail", false),

            // --- 기록 조회: 수치를 지어내지 말고 도구를 불러야 한다 ---
            new EvalCase("오늘 뭐 먹었지?", "get_meals_for_date", false),
            new EvalCase("어제 총 몇 칼로리 먹었어?", "get_daily_total", false),
            new EvalCase("요즘 체중 어때?", "get_inbody_history", false),
            new EvalCase("내 목표 섭취량 얼마야?", "calculate_nutrient_target", false),
            new EvalCase("내 BMI 또래랑 비교하면 어때?", "get_bmi_peer_comparison", false),
            new EvalCase("나 또래보다 많이 먹는 편이야?", "get_nutrition_peer_comparison", false),

            // --- 도구 없이 짧게 답해야 하는 턴 ---
            new EvalCase("안녕", null, false),
            new EvalCase("고마워", null, false),
            new EvalCase("너 누구야?", null, false)
    );

    private record Score(String prompt, boolean calledTool, boolean picksInCandidates, boolean koreanOnly, String reply) {}

    @Test
    void 운동_추천_회귀_평가() {
        OllamaClient client = buildClient();

        List<Score> scores = new ArrayList<>();
        for (EvalCase evalCase : CASES) {
            scores.add(run(client, evalCase));
        }

        report(scores);

        long toolOk = scores.stream().filter(Score::calledTool).count();
        long pickOk = scores.stream().filter(Score::picksInCandidates).count();
        long koreanOk = scores.stream().filter(Score::koreanOnly).count();

        assertTrue(toolOk >= CASES.size() * PASS_RATE,
                "도구 호출 정확도가 기준(%.0f%%) 아래입니다: %d/%d".formatted(PASS_RATE * 100, toolOk, CASES.size()));
        assertTrue(koreanOk >= CASES.size() * PASS_RATE,
                "한국어 답변 비율이 기준 아래입니다: %d/%d".formatted(koreanOk, CASES.size()));
        long pickCases = CASES.stream().filter(EvalCase::checkPicks).count();
        assertTrue(pickOk >= pickCases * PASS_RATE,
                "후보 밖 운동을 지어낸 턴이 많습니다: %d/%d".formatted(pickOk, pickCases));
    }

    private Score run(OllamaClient client, EvalCase evalCase) {
        List<OllamaMessage> messages = new ArrayList<>();
        messages.add(OllamaMessage.system(ChatService.SYSTEM_PROMPT));
        messages.add(OllamaMessage.user(evalCase.prompt()));

        OllamaClient.StreamResult first = client.chatCompletionStream(messages, true, delta -> {});
        List<OllamaMessage.ToolCall> toolCalls = first.toolCalls().isEmpty()
                // 텍스트로 샌 툴콜도 회수해서 센다 - 서비스가 회수하는 것과 같은 기준이어야 한다
                ? ToolCallTextParser.parse(first.content())
                : first.toolCalls();

        List<String> calledNames = toolCalls.stream().map(c -> c.function().name()).toList();
        boolean calledTool = evalCase.expectTool() == null
                ? calledNames.isEmpty()
                : calledNames.contains(evalCase.expectTool());

        if (toolCalls.isEmpty()) {
            // 도구를 안 부른 턴은 1라운드 본문이 곧 답변이다
            return new Score(evalCase.prompt(), calledTool, true, isKoreanOnly(first.content()), first.content());
        }

        // 도구를 부른 턴은 고정된 결과를 돌려주고 최종 답변을 받는다
        messages.add(new OllamaMessage("assistant", "", toolCalls, null));
        for (OllamaMessage.ToolCall call : toolCalls) {
            messages.add(OllamaMessage.tool(toolResultFor(call.function().name()), call.id()));
        }
        String reply = client.chatCompletionStream(messages, false, delta -> {}).content();

        boolean picksOk = !evalCase.checkPicks() || mentionsOnlyKnownExercises(reply);
        return new Score(evalCase.prompt(), calledTool, picksOk, isKoreanOnly(reply), reply);
    }

    private String toolResultFor(String toolName) {
        if ("recommend_exercises".equals(toolName)) {
            return FIXED_TOOL_RESULT;
        }
        // 추천 외의 도구는 (a)(c)만 보므로 "기록 없음"으로 통일한다 - DB도 AI 서버도 띄우지 않는다
        return "{\"note\":\"기록이 없어요.\",\"instruction\":\"없다고만 답하고 수치를 지어내지 마세요.\"}";
    }

    /**
     * 후보 밖 운동을 말했는지. 답변에 후보가 하나도 안 나오면 그것도 실패다 -
     * 도구 결과를 무시하고 자기 말로 답한 것이기 때문이다.
     */
    private boolean mentionsOnlyKnownExercises(String reply) {
        return FIXED_CANDIDATES.stream().anyMatch(reply::contains);
    }

    /**
     * 한자·일본어가 섞이지 않고, 단위 외의 영어 단어가 없는지.
     * (Qwen은 한국어로 답하다가 갑자기 중국어 문장을 끼워 넣는 턴이 있다 - 실측)
     */
    static boolean isKoreanOnly(String text) {
        if (text == null || text.isBlank()) {
            return false;
        }
        for (char c : text.toCharArray()) {
            if ((c >= 0x4E00 && c <= 0x9FFF) || (c >= 0x3040 && c <= 0x30FF)) {
                return false;  // 한자 / 일본어 가나
            }
        }
        for (String word : text.split("[^A-Za-z]+")) {
            if (word.length() >= 3 && !ALLOWED_ASCII_WORDS.contains(word.toLowerCase(Locale.ROOT))) {
                return false;
            }
        }
        return true;
    }

    private void report(List<Score> scores) {
        Map<String, Integer> totals = new LinkedHashMap<>();
        System.out.println("\n=== 챗봇 평가 결과 ===");
        System.out.printf("%-40s %-6s %-6s %-6s%n", "질문", "도구", "후보", "한국어");
        for (Score score : scores) {
            System.out.printf("%-40s %-6s %-6s %-6s%n",
                    trim(score.prompt()),
                    mark(score.calledTool()), mark(score.picksInCandidates()), mark(score.koreanOnly()));
            totals.merge("도구", score.calledTool() ? 1 : 0, Integer::sum);
            totals.merge("후보", score.picksInCandidates() ? 1 : 0, Integer::sum);
            totals.merge("한국어", score.koreanOnly() ? 1 : 0, Integer::sum);
        }
        System.out.println("합계 " + totals + " / " + scores.size() + "턴");

        // 실패한 턴은 원문을 남긴다 - 숫자만 보면 왜 틀렸는지 알 수 없다
        scores.stream()
                .filter(s -> !(s.calledTool() && s.picksInCandidates() && s.koreanOnly()))
                .forEach(s -> System.out.println("\n[실패] " + s.prompt() + "\n" + s.reply()));
    }

    private String trim(String text) {
        return text.length() <= 38 ? text : text.substring(0, 37) + "…";
    }

    private String mark(boolean ok) {
        return ok ? "O" : "X";
    }

    private OllamaClient buildClient() {
        String baseUrl = System.getenv().getOrDefault("CHAT_EVAL_OLLAMA_URL", "http://localhost:11434");
        String model = System.getenv().getOrDefault("CHAT_EVAL_MODEL", "qwen2.5:7b");
        System.out.println("평가 대상: " + model + " @ " + baseUrl);

        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(Duration.ofSeconds(3));
        factory.setReadTimeout(Duration.ofSeconds(120));
        RestClient restClient = RestClient.builder().baseUrl(baseUrl).requestFactory(factory).build();
        return new HttpOllamaClient(restClient, model, new ObjectMapper());
    }
}

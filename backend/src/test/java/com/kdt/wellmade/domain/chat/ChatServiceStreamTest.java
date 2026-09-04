package com.kdt.wellmade.domain.chat;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;

import org.junit.jupiter.api.Test;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.kdt.wellmade.domain.user.User;

/**
 * 1라운드 본문을 붙잡아뒀다가(홀드) 흘리는 로직 - 실제 모델에서 툴콜이 텍스트로 새는 턴은
 * 확률적으로만 나와서 재현이 어렵고, 잘못되면 사용자 화면에 JSON이 뜬다. 가짜 스트림으로 고정한다.
 */
class ChatServiceStreamTest {

    /** 스크립트대로 델타를 흘려보내는 가짜 Ollama. 라운드마다 하나씩 꺼내 쓴다. */
    private static final class FakeOllamaClient implements OllamaClient {

        private record Round(List<String> deltas, List<OllamaMessage.ToolCall> toolCalls) {}

        private final Deque<Round> rounds = new ArrayDeque<>();

        void round(List<String> deltas, List<OllamaMessage.ToolCall> toolCalls) {
            rounds.add(new Round(deltas, toolCalls));
        }

        @Override
        public OllamaMessage chatCompletion(List<OllamaMessage> messages, boolean includeTools) {
            throw new UnsupportedOperationException("이 테스트는 스트리밍 경로만 본다");
        }

        @Override
        public StreamResult chatCompletionStream(
                List<OllamaMessage> messages, boolean includeTools, Consumer<String> onDelta) {
            Round round = rounds.poll();
            if (round == null) {
                throw new IllegalStateException("스크립트에 없는 라운드가 호출됨");
            }
            StringBuilder content = new StringBuilder();
            for (String delta : round.deltas()) {
                content.append(delta);
                onDelta.accept(delta);
            }
            return new StreamResult(content.toString(), round.toolCalls());
        }
    }

    /** 사용자에게 실제로 나간 것만 남긴다 - reset이 오면 화면처럼 비운다 */
    private static final class Recorder implements ChatService.ReplyStream {
        private final StringBuilder shown = new StringBuilder();
        private int resets;

        @Override
        public void delta(String text) {
            shown.append(text);
        }

        @Override
        public void reset() {
            resets++;
            shown.setLength(0);
        }
    }

    /** 도구는 실제로 실행하지 않고 고정된 결과만 돌려준다 */
    private static final class FakeToolExecutor extends ChatToolExecutor {
        FakeToolExecutor() {
            super(null, null, null, null, null, new ObjectMapper());
        }

        @Override
        String execute(User user, String name, Map<String, Object> arguments) {
            return "{\"date\":\"2026-09-01\",\"meals\":[{\"menuName\":\"김밥\",\"kcal\":480}]}";
        }
    }

    private ChatService serviceWith(FakeOllamaClient ollama) {
        return new ChatService(null, null, null, null, null, ollama, new FakeToolExecutor(), new ObjectMapper());
    }

    private static List<OllamaMessage> messages() {
        return new ArrayList<>(List.of(OllamaMessage.user("어제 뭐 먹었지?")));
    }

    private static OllamaMessage.ToolCall mealsCall() {
        return new OllamaMessage.ToolCall(
                "call-1", new OllamaMessage.FunctionCall("get_meals_for_date", Map.of("date", "2026-09-01")));
    }

    /**
     * 붙잡아둔 본문이 툴콜처럼 보였는데 회수까지 실패한 경우. 예전엔 이 분기에서 홀드분을 그대로
     * 사용자에게 내보내서(그리고 이력에도 저장해서) 화면에 JSON이 떴다.
     */
    @Test
    void unparsableToolCallTextIsNeverShownToUser() {
        FakeOllamaClient ollama = new FakeOllamaClient();
        // 잡토큰이 JSON 중간에 껴서 파싱이 안 되는 형태. 48자를 넘겨도 툴콜처럼 보이니 계속 홀드된다.
        ollama.round(List.of(
                "<tool_call>{\"name\": \"get_meals_for_date\", ",
                "leton \"arguments\": {\"date\": \"2026-09-01\"}}"), List.of());

        Recorder recorder = new Recorder();
        String action = serviceWith(ollama).resolveToolsThenStream(null, messages(), recorder);

        // 아무것도 안 나가야 한다 - 빈 답변은 replyStream이 "답변을 만들지 못했어요"로 대체한다
        assertEquals("", recorder.shown.toString());
        assertEquals(0, recorder.resets);
        assertTrue(action == null);
    }

    /** 도구를 안 부르는 짧은 답변(48자 미만)은 홀드된 채로 끝나므로, 마지막에 마저 흘려야 한다 */
    @Test
    void shortPlainAnswerIsFlushedAtTheEnd() {
        FakeOllamaClient ollama = new FakeOllamaClient();
        ollama.round(List.of("안녕하세요!", " 무엇을 도와드릴까요?"), List.of());

        Recorder recorder = new Recorder();
        serviceWith(ollama).resolveToolsThenStream(null, messages(), recorder);

        assertEquals("안녕하세요! 무엇을 도와드릴까요?", recorder.shown.toString());
    }

    /**
     * 예고 문장을 길게 쓴 뒤에 도구를 부르는 턴. 예고문은 이미 사용자에게 흘러간 뒤라 최종 답변
     * 앞에 붙어 남는데, 2라운드 직전에 reset을 보내 말풍선을 비운다.
     */
    @Test
    void preambleShownBeforeToolCallIsClearedByReset() {
        FakeOllamaClient ollama = new FakeOllamaClient();
        // TOOLCALL_SNIFF_CHARS(48자)를 넘겨야 사용자에게 흘러나간다 - 그보다 짧으면 홀드된 채로 버려진다
        ollama.round(List.of("네, 어제 드신 식단을 확인해볼게요. 기록을 불러오는 중이니 잠시만 기다려 주세요. 곧 알려드릴게요."),
                List.of(mealsCall()));
        ollama.round(List.of("어제는 김밥 480kcal를 드셨어요."), List.of());

        Recorder recorder = new Recorder();
        serviceWith(ollama).resolveToolsThenStream(null, messages(), recorder);

        assertEquals(1, recorder.resets);
        assertEquals("어제는 김밥 480kcal를 드셨어요.", recorder.shown.toString());
    }

    /** 본문 없이 바로 도구를 부르는 흔한 경우엔 지울 게 없으니 reset도 보내지 않는다 */
    @Test
    void toolCallWithoutPreambleSendsNoReset() {
        FakeOllamaClient ollama = new FakeOllamaClient();
        ollama.round(List.of(), List.of(mealsCall()));
        ollama.round(List.of("어제는 김밥 480kcal를 드셨어요."), List.of());

        Recorder recorder = new Recorder();
        serviceWith(ollama).resolveToolsThenStream(null, messages(), recorder);

        assertEquals(0, recorder.resets);
        assertEquals("어제는 김밥 480kcal를 드셨어요.", recorder.shown.toString());
    }

    /** 텍스트로 샌 툴콜을 회수한 턴에서도 홀드분은 화면에 나가지 않는다 */
    @Test
    void recoveredToolCallTextIsNotShown() {
        FakeOllamaClient ollama = new FakeOllamaClient();
        ollama.round(List.of("<tool_call>{\"name\": \"get_meals_for_date\", \"arguments\": {\"date\": \"2026-09-01\"}}"),
                List.of());
        ollama.round(List.of("어제는 김밥 480kcal를 드셨어요."), List.of());

        Recorder recorder = new Recorder();
        serviceWith(ollama).resolveToolsThenStream(null, messages(), recorder);

        assertEquals("어제는 김밥 480kcal를 드셨어요.", recorder.shown.toString());
    }
}

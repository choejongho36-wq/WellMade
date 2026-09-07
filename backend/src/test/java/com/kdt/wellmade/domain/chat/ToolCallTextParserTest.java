package com.kdt.wellmade.domain.chat;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;

import org.junit.jupiter.api.Test;

/**
 * 모델이 도구 호출을 구조화된 tool_calls 대신 본문 텍스트로 흘리는 턴이 실제로 나온다.
 * 그걸 회수하지 못하면 도구가 안 돌고, 검증 안 된 답이 그대로 사용자에게 나가서 환각이 된다.
 */
class ToolCallTextParserTest {

    // Ollama에서 실제로 관측된 형태 - 앞에 잡토큰, 뒤에 닫는 태그가 붙어서 온다
    private static final String LEAKED = """
            leton
            {"name": "get_meals_for_date", "arguments": {"date": "2026-08-31"}}
            </tool_call>""";

    // 도구를 6개로 늘린 뒤 실제로 관측된 또 다른 유출 - 앞에 붙는 잡토큰은 매번 다르다
    private static final String LEAKED_PEER = """
            ONGL
            {"name": "get_nutrition_peer_comparison", "arguments": {"date": "2026-09-01"}}
            </tool_call>""";

    @Test
    void recoversPeerComparisonToolCallLeakedAsText() {
        assertTrue(ToolCallTextParser.looksLikeToolCall(LEAKED_PEER));

        List<OllamaMessage.ToolCall> calls = ToolCallTextParser.parse(LEAKED_PEER);
        assertEquals(1, calls.size());
        assertEquals("get_nutrition_peer_comparison", calls.get(0).function().name());
        assertEquals("2026-09-01", calls.get(0).function().arguments().get("date"));
    }

    @Test
    void recoversToolCallLeakedAsText() {
        assertTrue(ToolCallTextParser.looksLikeToolCall(LEAKED));

        List<OllamaMessage.ToolCall> calls = ToolCallTextParser.parse(LEAKED);
        assertEquals(1, calls.size());
        assertEquals("get_meals_for_date", calls.get(0).function().name());
        assertEquals("2026-08-31", calls.get(0).function().arguments().get("date"));
    }

    /** 회수한 호출의 결과를 tool 메시지로 되돌려줄 때 tool_call_id로 쓰이므로 비어 있으면 안 된다 */
    @Test
    void recoveredCallGetsAnId() {
        assertNotNull(ToolCallTextParser.parse(LEAKED).get(0).id());
    }

    // 운동 추천 도구를 넣은 뒤 사용자 화면에 그대로 노출된 형태 (2026-09-03 스크린샷).
    // <tool_call> 태그도 "name" 키도 없이 `도구이름 {인자}` 로만 흘러서, 예전 판별식은 못 잡았다.
    private static final String LEAKED_BARE_NAME =
            "dumpingbells, recommend_exercises {\"body_part\": \"어깨\", \"equipment\": \"덤벨\"}";

    @Test
    void recoversToolCallLeakedAsBareNameAndArgs() {
        assertTrue(ToolCallTextParser.looksLikeToolCall(LEAKED_BARE_NAME));

        List<OllamaMessage.ToolCall> calls = ToolCallTextParser.parse(LEAKED_BARE_NAME);
        assertEquals(1, calls.size());
        assertEquals("recommend_exercises", calls.get(0).function().name());
        assertEquals("어깨", calls.get(0).function().arguments().get("body_part"));
        assertEquals("덤벨", calls.get(0).function().arguments().get("equipment"));
    }

    @Test
    void plainAnswerIsNotMistakenForToolCall() {
        String normal = "어제는 기록된 식사가 없어요. 식단을 기록하면 확인해드릴게요.";
        assertFalse(ToolCallTextParser.looksLikeToolCall(normal));
        assertTrue(ToolCallTextParser.parse(normal).isEmpty());
    }

    @Test
    void jsonWithoutNameIsNotToolCall() {
        assertTrue(ToolCallTextParser.parse("{\"foo\": 1}").isEmpty());
    }

    /**
     * 툴콜처럼 보이는데 회수는 실패하는 경우들. 이 조합(보이긴 하는데 못 읽음)이 제일 위험하다 -
     * 이 텍스트를 사용자에게 그대로 흘리면 화면에 JSON이 뜬다
     * ({@link ChatServiceStreamTest}에서 실제로 안 나가는지 확인).
     */
    @Test
    void brokenJsonLooksLikeToolCallButIsNotRecovered() {
        // 잡토큰이 앞뒤가 아니라 JSON 중간에 낀 경우
        String garbageInside = "<tool_call>{\"name\": \"get_meals_for_date\", leton \"arguments\": {\"date\": \"2026-09-01\"}}";
        assertTrue(ToolCallTextParser.looksLikeToolCall(garbageInside));
        assertTrue(ToolCallTextParser.parse(garbageInside).isEmpty());
    }

    @Test
    void truncatedToolCallLooksLikeToolCallButIsNotRecovered() {
        // num_predict에 걸려 닫는 중괄호 전에 잘린 경우
        String truncated = "<tool_call>{\"name\": \"recommend_exercises\", \"arguments\": {\"body_part\": \"어";
        assertTrue(ToolCallTextParser.looksLikeToolCall(truncated));
        assertTrue(ToolCallTextParser.parse(truncated).isEmpty());
    }
}

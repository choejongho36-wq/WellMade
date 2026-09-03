package com.kdt.wellmade.domain.chat;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;

import org.junit.jupiter.api.Test;

/**
 * 모델이 도구 호출을 구조화된 tool_calls 대신 본문 텍스트로 흘리는 턴이 실제로 나온다.
 * 그걸 회수하지 못하면 도구가 안 돌고, 검증 안 된 답이 그대로 사용자에게 나가서 환각이 된다.
 */
class ChatServiceToolCallTextTest {

    // 생성자는 필드 대입만 하므로 파싱 로직만 보려면 이걸로 충분함
    private final ChatService service = new ChatService(null, null, null, null, null, null, null);

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
        assertTrue(service.looksLikeToolCallText(LEAKED_PEER));

        List<OllamaMessage.ToolCall> calls = service.parseToolCallsFromText(LEAKED_PEER);
        assertEquals(1, calls.size());
        assertEquals("get_nutrition_peer_comparison", calls.get(0).function().name());
        assertEquals("2026-09-01", calls.get(0).function().arguments().get("date"));
    }

    @Test
    void recoversToolCallLeakedAsText() {
        assertTrue(service.looksLikeToolCallText(LEAKED));

        List<OllamaMessage.ToolCall> calls = service.parseToolCallsFromText(LEAKED);
        assertEquals(1, calls.size());
        assertEquals("get_meals_for_date", calls.get(0).function().name());
        assertEquals("2026-08-31", calls.get(0).function().arguments().get("date"));
    }

    @Test
    void plainAnswerIsNotMistakenForToolCall() {
        String normal = "어제는 기록된 식사가 없어요. 식단을 기록하면 확인해드릴게요.";
        assertFalse(service.looksLikeToolCallText(normal));
        assertTrue(service.parseToolCallsFromText(normal).isEmpty());
    }

    @Test
    void jsonWithoutNameIsNotToolCall() {
        assertTrue(service.parseToolCallsFromText("{\"foo\": 1}").isEmpty());
    }
}

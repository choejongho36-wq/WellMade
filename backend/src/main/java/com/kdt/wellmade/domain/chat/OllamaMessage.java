package com.kdt.wellmade.domain.chat;

import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.annotation.JsonInclude;

/**
 * Ollama /api/chat 프로토콜 전용 메시지 표현.
 *
 * 컨트롤러에 노출되는 공개 DTO {@link ChatMessage}(role, content)는 프론트와의 계약이라 함부로
 * 못 바꾸지만, 내부적으로 Ollama와 주고받을 때는 tool_calls(모델이 도구 호출을 요청)와
 * tool_call_id(도구 실행 결과를 어떤 호출에 대한 응답인지 표시)까지 필요해서 별도로 둠.
 *
 * NON_NULL: 이게 없으면 대부분의 메시지에 쓸모없는 "tool_calls":null,"tool_call_id":null 이
 * 같이 실려나간다. 매 턴 이력까지 통째로 보내므로 요청 크기·프리필 토큰이 그만큼 늘어남.
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public record OllamaMessage(
        String role,
        String content,
        List<ToolCall> tool_calls,
        String tool_call_id
) {
    public static OllamaMessage system(String content) {
        return new OllamaMessage("system", content, null, null);
    }

    public static OllamaMessage user(String content) {
        return new OllamaMessage("user", content, null, null);
    }

    public static OllamaMessage assistant(String content) {
        return new OllamaMessage("assistant", content, null, null);
    }

    public static OllamaMessage tool(String content, String toolCallId) {
        return new OllamaMessage("tool", content, null, toolCallId);
    }

    public record ToolCall(String id, FunctionCall function) {}

    public record FunctionCall(String name, Map<String, Object> arguments) {}
}

package com.kdt.wellmade.domain.chat;

import java.util.List;
import java.util.function.Consumer;

/**
 * Ollama /api/chat 호출 창구. 구현은 {@link HttpOllamaClient} 하나뿐이지만, 인터페이스로 둬야
 * {@link ChatService}의 홀드/릴리즈·2라운드 로직을 가짜 스트림으로 테스트할 수 있다
 * (실제 모델은 툴콜을 텍스트로 흘리는 턴이 확률적으로만 나와서 재현이 어렵다).
 */
public interface OllamaClient {

    String AI_UNAVAILABLE_MSG = "AI 챗봇은 지금 준비 중이에요. 잠시 후 다시 시도해 주세요.";

    /** 스트리밍 한 번의 결과 - 흘려보낸 본문과, 모델이 요청한 도구 호출 목록 */
    record StreamResult(String content, List<OllamaMessage.ToolCall> toolCalls) {}

    /** 비스트리밍 호출. 응답 message를 그대로 돌려준다(content가 null일 수 있음). */
    OllamaMessage chatCompletion(List<OllamaMessage> messages, boolean includeTools);

    /**
     * stream 모드로 호출해서, 응답으로 오는 NDJSON 각 줄의 message.content 조각을
     * 받는 대로 {@code onDelta}에 넘긴다.
     * tools를 포함해 호출한 경우 도중에 오는 message.tool_calls를 모아서 돌려준다.
     */
    StreamResult chatCompletionStream(List<OllamaMessage> messages, boolean includeTools, Consumer<String> onDelta);
}

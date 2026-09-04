package com.kdt.wellmade.domain.chat;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.kdt.wellmade.global.exception.ExternalServiceException;

/**
 * 로컬 Ollama(/api/chat) 호출만 담당한다 - 요청 본문 구성, 스트리밍/비스트리밍 호출, 실패를
 * 사용자向 예외로 변환. 대화 구성이나 도구 실행은 ChatService/ChatToolExecutor 쪽 일이다.
 */
@Component
public class HttpOllamaClient implements OllamaClient {

    private static final Logger log = LoggerFactory.getLogger(HttpOllamaClient.class);

    private final RestClient ollamaRestClient;
    private final String model;
    private final ObjectMapper objectMapper;

    public HttpOllamaClient(
            RestClient ollamaRestClient, @Value("${ollama.model}") String model, ObjectMapper objectMapper) {
        this.ollamaRestClient = ollamaRestClient;
        this.model = model;
        this.objectMapper = objectMapper;
    }

    private record OllamaChatResponse(OllamaMessage message) {
    }

    @Override
    public OllamaMessage chatCompletion(List<OllamaMessage> messages, boolean includeTools) {
        OllamaChatResponse response;
        try {
            response = ollamaRestClient.post()
                    .uri("/api/chat")
                    .body(buildRequestBody(messages, includeTools, false))
                    .retrieve()
                    .body(OllamaChatResponse.class);
        } catch (RestClientException e) {
            throw aiUnavailable(e);
        }

        if (response == null || response.message() == null) {
            log.error("Ollama 채팅 응답이 비어있습니다.");
            throw new ExternalServiceException(AI_UNAVAILABLE_MSG);
        }
        return response.message();
    }

    @Override
    public StreamResult chatCompletionStream(
            List<OllamaMessage> messages, boolean includeTools, Consumer<String> onDelta
    ) {
        StringBuilder content = new StringBuilder();
        List<OllamaMessage.ToolCall> toolCalls = new ArrayList<>();
        try {
            ollamaRestClient.post()
                    .uri("/api/chat")
                    .body(buildRequestBody(messages, includeTools, true))
                    .exchange((request, response) -> {
                        try (BufferedReader reader = new BufferedReader(
                                new InputStreamReader(response.getBody(), StandardCharsets.UTF_8))) {
                            String line;
                            while ((line = reader.readLine()) != null) {
                                if (line.isBlank()) {
                                    continue;
                                }
                                JsonNode node = objectMapper.readTree(line);
                                JsonNode message = node.path("message");

                                String delta = message.path("content").asText("");
                                if (!delta.isEmpty()) {
                                    content.append(delta);
                                    try {
                                        onDelta.accept(delta);
                                    } catch (RuntimeException e) {
                                        // 받는 쪽(SSE)이 던진 것 - 아래 catch에서 Ollama 장애로
                                        // 오해하지 않도록 표시해서 올려보낸다
                                        throw new DeltaConsumerException(e);
                                    }
                                }
                                collectToolCalls(message, toolCalls);

                                if (node.path("done").asBoolean(false)) {
                                    break;
                                }
                            }
                        } catch (java.io.IOException e) {
                            throw new UncheckedIOException(e);
                        }
                        return null;
                    });
        } catch (DeltaConsumerException e) {
            // 흔한 원인은 사용자가 답변 도중 창을 닫은 것(SseEmitter 전송 실패). Ollama는 멀쩡하므로
            // "AI 준비 중" 안내로 바꾸지 않고 원래 예외를 그대로 올린다.
            throw e.getCause();
        } catch (RestClientException | UncheckedIOException e) {
            throw aiUnavailable(e);
        }
        return new StreamResult(content.toString(), toolCalls);
    }

    /** onDelta(응답을 받아가는 쪽)가 던진 예외를 Ollama 자체의 실패와 구분하기 위한 표시 */
    private static final class DeltaConsumerException extends RuntimeException {
        DeltaConsumerException(RuntimeException cause) {
            super(cause);
        }

        @Override
        public synchronized RuntimeException getCause() {
            return (RuntimeException) super.getCause();
        }
    }

    /** 스트림 조각에 들어있는 tool_calls를 자바 객체로 옮겨 담는다 (없으면 아무것도 안 함) */
    private void collectToolCalls(JsonNode message, List<OllamaMessage.ToolCall> into) {
        JsonNode calls = message.path("tool_calls");
        if (!calls.isArray()) {
            return;
        }
        for (JsonNode call : calls) {
            JsonNode function = call.path("function");
            Map<String, Object> arguments = objectMapper.convertValue(
                    function.path("arguments"), new TypeReference<Map<String, Object>>() {});
            into.add(new OllamaMessage.ToolCall(
                    call.path("id").asText(null),
                    new OllamaMessage.FunctionCall(function.path("name").asText(), arguments)
            ));
        }
    }

    private Map<String, Object> buildRequestBody(List<OllamaMessage> messages, boolean includeTools, boolean stream) {
        Map<String, Object> requestBody = new LinkedHashMap<>();
        requestBody.put("model", model);
        requestBody.put("stream", stream);
        requestBody.put("messages", messages);
        // Ollama는 마지막 요청 후 5분이 지나면 모델(4.7GB)을 메모리에서 내린다. 챗봇은 띄엄띄엄
        // 쓰이므로 그대로 두면 사용자가 거의 매번 재적재(20초 안팎)를 기다리게 된다.
        // GPU 인스턴스 환경변수를 건드리지 않고 요청마다 상주 시간을 지정해 그 비용을 없앤다.
        requestBody.put("keep_alive", "24h");
        // temperature 미지정 시 Ollama 기본값(0.8)이 적용되던 걸 명시적으로 낮춤.
        // num_ctx: 시스템 프롬프트(약 1000토큰) + 툴 스키마(약 800) + 이력 8건 + 답변 384가
        // 4096을 넘길 수 있었다. 넘치면 Ollama가 앞쪽부터 버려서 시스템 프롬프트가 날아간다.
        // *** FoodParsingService와 값이 반드시 같아야 함 *** - 같은 모델을 쓰는데 num_ctx가
        // 다르면 Ollama가 요청마다 모델을 내렸다 다시 올린다(4.7GB 재적재 = 20초).
        // temperature 0.4에서는 모델이 도구를 부르는 대신 예고 문장만 쓰거나 tool_call을 텍스트로
        // 흘리는 턴이 나온다(재현: 12회 중 1회). 도구가 안 돌면 검증 없는 답이 그대로 나가고
        // 그게 이력에 남아 다음 턴부터 증폭되므로, 다양성보다 툴콜 신뢰도를 택한다.
        requestBody.put("options", Map.of(
                "temperature", 0.2,
                "num_ctx", 8192,
                "num_predict", 384
        ));
        if (includeTools) {
            requestBody.put("tools", ChatToolExecutor.TOOLS);
        }
        return requestBody;
    }

    /**
     * Ollama 호출 실패를 사용자向 예외로 변환한다. Ollama(GPU 인스턴스)는 평소 꺼져 있는 게 정상이라,
     * 연결 자체가 안 되는 경우({@link ResourceAccessException} - ConnectException/타임아웃)는
     * 스택트레이스 없이 INFO로만 남긴다. 그 외(5xx 응답 등)만 ERROR.
     */
    private ExternalServiceException aiUnavailable(Exception e) {
        if (e instanceof ResourceAccessException) {
            log.info("Ollama에 연결할 수 없음 (GPU 인스턴스 중지 상태로 추정): {}", e.getMessage());
        } else {
            log.error("Ollama 호출 실패", e);
        }
        return new ExternalServiceException(AI_UNAVAILABLE_MSG, e);
    }
}

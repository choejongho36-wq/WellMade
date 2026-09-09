package com.kdt.wellmade.domain.chat;

import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

/**
 * 모델이 구조화된 tool_calls 대신 본문 텍스트로 흘려보낸 도구 호출을 판별하고 회수한다.
 *
 * Qwen이 도구 호출을 {@code <tool_call>{"name":...}} 같은 텍스트로 흘리는 턴이 실제로 나오는데,
 * 그대로 스트리밍하면 화면에 JSON이 뜨고 도구도 안 돌아서 검증 안 된 답이 나간다.
 * 대화 구성과 무관한 순수 함수라 {@link ChatService}에서 떼어냈다(가장 깨지기 쉬운 로직이라 테스트가 필요함).
 */
final class ToolCallTextParser {

    private static final Logger log = LoggerFactory.getLogger(ToolCallTextParser.class);

    private static final ObjectMapper MAPPER = new ObjectMapper();

    private ToolCallTextParser() {
    }

    /**
     * "확인해보겠습니다"처럼 도구를 부르겠다는 예고. 정상 답변에는 "확인해보세요"(권유)는 나와도
     * 1인칭 미래형은 안 나온다. 데이터를 이미 인용한 답(kcal, kg, 세트)은 예고가 아니다.
     */
    private static final List<String> PREAMBLE_HINTS = List.of(
            "확인해보겠", "확인해 보겠", "확인해볼게", "확인해 볼게", "확인하겠", "확인할게", "확인 중",
            "찾아보겠", "찾아볼게", "불러오겠", "불러올게", "불러오는 중", "알아보겠", "알아볼게",
            "조회해보겠", "조회하겠", "조회할게", "살펴보겠", "살펴볼게", "가져오겠", "가져올게");

    /** 예고문이라도 이보다 길면 뒤에 실제 답이 이어진 것으로 본다 */
    private static final int PREAMBLE_MAX_CHARS = 200;

    /**
     * 본문이 "도구를 부르겠다"는 예고만 하고 끝났는지. 모델이 규칙("예고만 쓰고 끝내지 말 것")을
     * 어기고 이렇게 답하는 턴이 실제로 나온다(실측: "최근 섭취 기록을 확인해보겠습니다."로 끝).
     * 그대로 내보내면 대화가 거기서 멈추고, 이력에 남아 다음 턴에 똑같이 반복된다.
     */
    static boolean isPreambleOnly(String content) {
        if (content == null || content.isBlank() || content.length() > PREAMBLE_MAX_CHARS) {
            return false;
        }
        if (content.contains("kcal") || content.contains("kg") || content.contains("세트")) {
            return false;
        }
        return PREAMBLE_HINTS.stream().anyMatch(content::contains);
    }

    /**
     * 본문이 모델이 텍스트로 흘린 도구 호출인지. 정상 답변이 이렇게 생길 일은 없다.
     *
     * 도구 이름까지 보는 이유: 예전엔 {@code <tool_call>} 태그나 {@code "name"} 키만 찾았는데,
     * 모델이 그 둘 없이 `recommend_exercises {"body_part": "어깨"}` 처럼 이름 + 인자만 흘리는
     * 턴이 실제로 나왔다(사용자 화면에 그대로 노출됨). 도구 이름은 정상 한국어 답변에 나올 말이 아니다.
     */
    static boolean looksLikeToolCall(String content) {
        if (content == null) {
            return false;
        }
        if (content.contains("<tool_call>") || content.contains("\"name\"")) {
            return true;
        }
        return ChatToolExecutor.TOOL_NAMES.stream().anyMatch(content::contains);
    }

    /**
     * 본문으로 샌 도구 호출을 회수한다. 앞뒤에 잡토큰(`leton`, `</tool_call>`)이 붙어 나오므로
     * 첫 '{'부터 마지막 '}'까지만 떼어 파싱한다. 실패하면 빈 목록.
     *
     * 빈 목록이 곧 "도구 없이 답한 턴"은 아니다 - 홀드 중이던 본문이 툴콜처럼 보였는데 여기서
     * 실패했다면 그건 회수 실패이고, 그 텍스트를 사용자에게 내보내면 안 된다
     * ({@link ChatService#resolveToolsThenStream} 참고).
     */
    static List<OllamaMessage.ToolCall> parse(String content) {
        if (content == null) {
            return List.of();
        }
        int start = content.indexOf('{');
        int end = content.lastIndexOf('}');
        if (start < 0 || end <= start) {
            return List.of();
        }
        try {
            JsonNode node = MAPPER.readTree(content.substring(start, end + 1));

            // 형태 1 - {"name": "...", "arguments": {...}}
            String name = node.path("name").asText("");
            if (!name.isEmpty()) {
                Map<String, Object> arguments = MAPPER.convertValue(
                        node.path("arguments"), new TypeReference<Map<String, Object>>() {});
                log.warn("모델이 도구 호출을 본문 텍스트로 흘려서 회수함: {}", name);
                return List.of(toolCall(name, arguments));
            }

            // 형태 2 - `recommend_exercises {"body_part": "어깨"}` 처럼 이름이 JSON 밖에 있고
            // 중괄호 안은 인자만 있는 경우. 이때는 JSON 전체가 arguments다.
            String bareName = ChatToolExecutor.TOOL_NAMES.stream()
                    .filter(n -> content.lastIndexOf(n, start) >= 0)
                    .findFirst()
                    .orElse(null);
            if (bareName == null) {
                return List.of();
            }
            Map<String, Object> arguments = MAPPER.convertValue(
                    node, new TypeReference<Map<String, Object>>() {});
            log.warn("모델이 도구 호출을 '이름 + 인자' 텍스트로 흘려서 회수함: {}", bareName);
            return List.of(toolCall(bareName, arguments));
        } catch (Exception e) {
            return List.of();
        }
    }

    /**
     * id는 Ollama가 준 게 아니라 우리가 만든다 - 도구 결과 메시지의 tool_call_id로 그대로 쓰이는데,
     * null로 두면 어떤 호출에 대한 응답인지 표시가 빠진 채로 나간다(Ollama는 무시하지만 굳이 비울 이유가 없음).
     */
    private static OllamaMessage.ToolCall toolCall(String name, Map<String, Object> arguments) {
        return new OllamaMessage.ToolCall(
                "text-" + UUID.randomUUID(), new OllamaMessage.FunctionCall(name, arguments));
    }
}

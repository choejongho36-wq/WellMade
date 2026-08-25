package com.kdt.wellmade.domain.nutrition;


import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;
 
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
 
/**
 * Ollama에서 돌고 있는 Qwen에게 자유텍스트 메뉴를 보내서
 * "음식명 + 추정 그램수" 리스트를 JSON으로 파싱받는 서비스.
 *
 * *** 파인튜닝 안 된 원본 Qwen 사용 - 프롬프트 안에 few-shot 예시를 넣어서 유도하는 방식 ***
 *
 * 사전 준비:
 *   1. Ollama 설치 (https://ollama.com)
 *   2. ollama pull qwen2.5:7b-instruct   (또는 VRAM 상황에 따라 qwen2.5:3b-instruct)
 *   3. ollama serve 로 로컬에서 실행 (기본 포트 11434)
 */
@Service
public class FoodParsingService {
 
    private static final String SYSTEM_PROMPT = """
            당신은 사용자가 말한 식사 메시지에서 음식 항목과 추정 섭취량(그램)을 추출하는 도구입니다.
            반드시 JSON 배열로만 답하세요. 다른 설명이나 마크다운 코드블록 없이 순수 JSON만 출력하세요.
 
            규칙:
            - 각 항목은 {"foodName": "음식명", "amountG": 숫자} 형태
            - foodName은 검색하기 쉬운 일반적인 명칭으로 정규화하세요 (예: "김치찌개", "흰쌀밥")
            - amountG은 일반적인 1인분 기준으로 상식적으로 추정하세요 (모르면 표준 1인분량 사용)
            - "한공기", "한그릇" 같은 표현은 일반적인 그램수로 환산하세요 (밥 한공기 ≈ 210g)
 
            예시 입력: "점심에 김치찌개랑 밥 한공기 먹었어요"
            예시 출력: [{"foodName": "김치찌개", "amountG": 400}, {"foodName": "흰쌀밥", "amountG": 210}]
 
            예시 입력: "아침에 계란후라이 2개랑 식빵 두쪽 먹음"
            예시 출력: [{"foodName": "계란후라이", "amountG": 100}, {"foodName": "식빵", "amountG": 70}]
            """;
 
    private final String ollamaBaseUrl;
    private final String ollamaModel;
    private final RestTemplate restTemplate = new RestTemplate();
    private final ObjectMapper objectMapper = new ObjectMapper();
 
    public FoodParsingService(
            @Value("${ollama.base-url:http://localhost:11434}") String ollamaBaseUrl,
            @Value("${ollama.model:qwen2.5:7b-instruct}") String ollamaModel
    ) {
        this.ollamaBaseUrl = ollamaBaseUrl;
        this.ollamaModel = ollamaModel;
    }
 
    public List<FoodItem> parse(String userMessage) {
        if (userMessage == null || userMessage.isBlank()) {
            throw new IllegalArgumentException("메시지를 입력해주세요.");
        }

        Map<String, Object> requestBody = Map.of(
                "model", ollamaModel,
                "messages", List.of(
                        Map.of("role", "system", "content", SYSTEM_PROMPT),
                        Map.of("role", "user", "content", userMessage)
                ),
                "stream", false
        );
 
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        HttpEntity<Map<String, Object>> request = new HttpEntity<>(requestBody, headers);
 
        String responseJson = restTemplate.postForObject(
                ollamaBaseUrl + "/api/chat", request, String.class);
 
        return parseResponse(responseJson);
    }
 
    private List<FoodItem> parseResponse(String responseJson) {
        try {
            JsonNode root = objectMapper.readTree(responseJson);
            String modelText = root.path("message").path("content").asText();
 
            String cleaned = modelText.trim()
                    .replaceAll("^```json\\s*", "")
                    .replaceAll("^```\\s*", "")
                    .replaceAll("```\\s*$", "")
                    .trim();
 
            JsonNode itemsArray = objectMapper.readTree(cleaned);
            List<FoodItem> items = new ArrayList<>();
            for (JsonNode item : itemsArray) {
                String name = item.path("foodName").asText();
                double amount = item.path("amountG").asDouble();
                items.add(new FoodItem(name, amount));
            }
            return items;
        } catch (Exception e) {
            throw new RuntimeException("Qwen 응답 파싱 실패. 원문: " + responseJson, e);
        }
    }
 
    public record FoodItem(String foodName, double amountG) {}
}
 
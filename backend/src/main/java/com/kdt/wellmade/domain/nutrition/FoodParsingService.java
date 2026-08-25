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
            - 각 항목은 {"foodName": "기록에 남길 이름", "searchName": "DB 검색용 기본 제품명", "amountG": 숫자} 형태
            - 집밥/조리음식처럼 통칭이 있는 음식은 foodName/searchName 둘 다 검색하기 쉬운 일반적인 명칭으로 정규화하세요 (예: "김치찌개", "흰쌀밥")
            - 과자, 음료, 라면 등 브랜드/제품명이 있는 가공식품은 그 이름을 그대로 유지하세요.
              절대 더 넓은 카테고리 명칭으로 뭉뚱그리지 마세요 (정답: "포카칩", 오답: "감자칩")
            - "큰 봉지", "패밀리사이즈", "라지" 등 용량을 나타내는 표현이 붙으면:
              foodName에는 그 표현까지 그대로 포함하고(예: "포카칩 큰 봉지"),
              searchName에는 DB 검색에 쓸 기본 제품명만 넣으세요(예: "포카칩").
              용량 표현이 없으면 foodName과 searchName은 같은 값입니다.
            - amountG은 일반적인 1인분/1봉지 기준으로 상식적으로 추정하세요 (모르면 표준량 사용).
              "큰 봉지"처럼 더 큰 용량이면 그에 맞게 amountG도 늘려서 추정하세요.
            - "한공기", "한그릇" 같은 표현은 일반적인 그램수로 환산하세요 (밥 한공기 ≈ 210g)
            - 가공식품은 실제 판매 포장 단위를 기준으로 추정하세요 (과자 한봉지 ≈ 60~70g, 큰 봉지 ≈ 130~140g)

            예시 입력: "점심에 김치찌개랑 밥 한공기 먹었어요"
            예시 출력: [{"foodName": "김치찌개", "searchName": "김치찌개", "amountG": 400}, {"foodName": "흰쌀밥", "searchName": "흰쌀밥", "amountG": 210}]

            예시 입력: "아침에 계란후라이 2개랑 식빵 두쪽 먹음"
            예시 출력: [{"foodName": "계란후라이", "searchName": "계란후라이", "amountG": 100}, {"foodName": "식빵", "searchName": "식빵", "amountG": 70}]

            예시 입력: "간식으로 포카칩 한봉지 먹었어요"
            예시 출력: [{"foodName": "포카칩", "searchName": "포카칩", "amountG": 66}]

            예시 입력: "포카칩 큰 봉지 하나 다 먹었어요"
            예시 출력: [{"foodName": "포카칩 큰 봉지", "searchName": "포카칩", "amountG": 135}]
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
                String searchName = item.path("searchName").asText("");
                double amount = item.path("amountG").asDouble();
                items.add(new FoodItem(name, searchName.isBlank() ? name : searchName, amount));
            }
            return items;
        } catch (Exception e) {
            throw new RuntimeException("Qwen 응답 파싱 실패. 원문: " + responseJson, e);
        }
    }

    /**
     * foodName: 기록에 남기는 이름 (사용자가 말한 그대로, 예: "포카칩 큰 봉지")
     * searchName: DB 검색에 쓰는 기본 제품명 (용량 표현 제거, 예: "포카칩")
     */
    public record FoodItem(String foodName, String searchName, double amountG) {}
}
 
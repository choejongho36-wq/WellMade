package com.kdt.wellmade.domain.nutrition;


import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import com.kdt.wellmade.global.exception.ExternalServiceException;
 
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

    private static final Logger log = LoggerFactory.getLogger(FoodParsingService.class);
 
    private static final String SYSTEM_PROMPT = """
            당신은 사용자가 말한 식사 메시지에서 음식 항목과 섭취량을 추출하는 도구입니다.
            반드시 {"items": [...]} 형태의 JSON 객체로만 답하세요. 다른 설명이나 마크다운 코드블록 없이 순수 JSON만 출력하세요.
            (Ollama의 JSON 모드는 최상위가 객체여야만 하므로, 배열을 바로 반환하지 말고 반드시 items 키로 감쌀 것)

            규칙:
            - items 배열의 각 항목은 {"foodName": "기록에 남길 이름", "searchName": "DB 검색용 기본 제품명", "amountG": 숫자 또는 null, "servings": 숫자} 형태
            - 집밥/조리음식처럼 통칭이 있는 음식은 foodName/searchName 둘 다 검색하기 쉬운 일반적인 명칭으로 정규화하세요 (예: "김치찌개", "흰쌀밥")
            - 과자, 음료, 라면 등 마트/편의점에서 그대로 사서 먹는 포장 가공식품은 브랜드/제품명을 그대로 유지하세요.
              절대 더 넓은 카테고리 명칭으로 뭉뚱그리지 마세요 (정답: "포카칩", 오답: "감자칩")
            - 엽기떡볶이, 파리바게트, 샐러디, 스타벅스, 교촌치킨처럼 매장에서 조리/제공하는 외식 프랜차이즈
              메뉴는 위와 다릅니다 - DB에는 프랜차이즈별 메뉴가 없고 일반적인 음식 통칭만 있으므로,
              foodName에는 사용자가 말한 브랜드+메뉴명을 그대로 남기되(기록에는 어디서 먹었는지 남아야 하니까),
              searchName에는 브랜드명을 떼고 그 요리가 속하는 일반적인 통칭만 넣으세요
              (예: "엽기떡볶이" -> searchName "떡볶이", "샐러디 탄단지 샐러드" -> searchName "닭가슴살 샐러드").
            - "큰 봉지", "패밀리사이즈", "라지" 등 용량을 나타내는 표현이 붙으면:
              foodName에는 그 표현까지 그대로 포함하고(예: "포카칩 큰 봉지"),
              searchName에는 DB 검색에 쓸 기본 제품명만 넣으세요(예: "포카칩").
              용량 표현이 없으면 foodName과 searchName은 같은 값입니다.
            - searchName은 foodName보다 더 구체적이면 안 됩니다. 사용자가 말하지 않은 단어를 붙여
              제품을 특정하지 마세요 (오답: "토스트" -> "토스트칩", "빵" -> "식빵").
              브랜드/용량 표현을 떼는 방향으로만 줄이고, 그 외에는 사용자가 말한 이름을 그대로 쓰세요.

            *** amountG / servings 판단 기준 - 그램수는 최대한 직접 추정하지 말고 DB의 표준중량에 맡길 것 ***
            - 사용자가 그램/ml 숫자를 명시적으로 말한 경우에만("200g", "300그램", "500ml") amountG에 그 숫자를 넣고 servings는 1로 두세요.
              이 경우엔 DB 표준중량을 무시하고 사용자가 말한 그램을 그대로 씁니다.
            - 그 외 모든 경우(수량/인분수만 말했거나 아무 표현이 없는 경우)는 amountG를 null로 두고 servings에 인분수를 넣으세요.
              DB에 저장된 1인분 기준중량 × servings로 서버가 그램을 계산합니다 - 그램수를 스스로 추정하지 마세요.
              - "1인분", "한그릇", "한공기"처럼 명시가 없거나 기본 단위 하나면 servings: 1
              - "2인분", "라면 2개", "계란후라이 2개"처럼 개수/인분이 명시되면 그 숫자를 servings에
              - "큰 봉지", "패밀리사이즈", "라지"처럼 용량이 커지는 표현은 기본 크기 대비 대략 몇 배인지
                상식적으로 판단해서 servings를 늘리세요 (예: 큰 봉지 ≈ 보통 대비 2배 -> servings: 2)
            - "한공기", "한그릇" 같은 표현은 servings 1로 두면 됩니다 (그램 환산은 DB 표준중량이 담당)

            예시 입력: "점심에 김치찌개랑 밥 한공기 먹었어요"
            예시 출력: {"items": [{"foodName": "김치찌개", "searchName": "김치찌개", "amountG": null, "servings": 1}, {"foodName": "흰쌀밥", "searchName": "멥쌀밥", "amountG": null, "servings": 1}]}

            예시 입력: "아침에 계란후라이 2개랑 식빵 두쪽 먹음"
            예시 출력: {"items": [{"foodName": "계란후라이", "searchName": "계란후라이", "amountG": null, "servings": 2}, {"foodName": "식빵", "searchName": "식빵", "amountG": null, "servings": 2}]}

            예시 입력: "간식으로 포카칩 한봉지 먹었어요"
            예시 출력: {"items": [{"foodName": "포카칩", "searchName": "포카칩", "amountG": null, "servings": 1}]}

            예시 입력: "포카칩 큰 봉지 하나 다 먹었어요"
            예시 출력: {"items": [{"foodName": "포카칩 큰 봉지", "searchName": "포카칩", "amountG": null, "servings": 2}]}

            예시 입력: "엽기떡볶이 2인분 먹었어"
            예시 출력: {"items": [{"foodName": "엽기떡볶이", "searchName": "떡볶이", "amountG": null, "servings": 2}]}

            예시 입력: "샐러디 탄단지 샐러드 먹었어"
            예시 출력: {"items": [{"foodName": "샐러디 탄단지 샐러드", "searchName": "닭가슴살 샐러드", "amountG": null, "servings": 1}]}

            예시 입력: "파리바게트 초코소라빵 먹었어"
            예시 출력: {"items": [{"foodName": "파리바게트 초코소라빵", "searchName": "초코소라빵", "amountG": null, "servings": 1}]}

            예시 입력: "닭가슴살 200g 먹었어"
            예시 출력: {"items": [{"foodName": "닭가슴살", "searchName": "닭가슴살", "amountG": 200, "servings": 1}]}
            """;
 
    /**
     * 인터넷 신조어/줄임말 -> 정식 명칭 치환 사전.
     *
     * "두쫀쿠"(두바이 쫀득 쿠키) 같은 최신 줄임말은 Qwen이 통째로 모르는 토큰이라, format:"json" 모드에서
     * foodName까지 깨진 문자열("두 komment" 등)로 뱉어버림 - "멥쌀밥" 문제와 달리 foodName 자체가
     * 깨져서 나중에 코드로 보정할 실마리도 없음. 그래서 모델한테 보내기 "전에" 원문 문자열을 정식 명칭으로
     * 미리 바꿔치기함 (모델은 "두바이 쫀득 쿠키"라는 표현은 정상적으로 잘 처리함).
     *
     * ponytail: 새 줄임말이 뜰 때마다 여기 한 줄씩 추가해야 함 - 끝없이 늘어나는 목록이라 규모가 커지면
     * DB 테이블로 옮기는 게 나을 수 있음.
     */
    private static final Map<String, String> SLANG_ALIASES = Map.of(
            "두쫀쿠", "두바이 쫀득 쿠키"
    );

    private final RestClient ollamaRestClient;
    private final String ollamaModel;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public FoodParsingService(
            RestClient ollamaRestClient,
            @Value("${ollama.model:qwen2.5:7b-instruct}") String ollamaModel
    ) {
        this.ollamaRestClient = ollamaRestClient;
        this.ollamaModel = ollamaModel;
    }

    public List<FoodItem> parse(String rawUserMessage) {
        if (rawUserMessage == null || rawUserMessage.isBlank()) {
            throw new IllegalArgumentException("메시지를 입력해주세요.");
        }
        String userMessage = expandSlang(rawUserMessage);

        Map<String, Object> requestBody = Map.of(
                "model", ollamaModel,
                "messages", List.of(
                        Map.of("role", "system", "content", SYSTEM_PROMPT),
                        Map.of("role", "user", "content", userMessage)
                ),
                "stream", false,
                // JSON 항목만 뽑아내는 작업인데 온도가 기본값(0.8)이라 형식이 흔들릴 여지가 컸음.
                // format:"json"으로 출력 자체를 강제하고 temperature:0으로 결정적으로 만듦.
                "format", "json",
                "options", Map.of("temperature", 0, "num_ctx", 4096)
        );
 
        String responseJson;
        try {
            responseJson = ollamaRestClient.post()
                    .uri("/api/chat")
                    .body(requestBody)
                    .retrieve()
                    .body(String.class);
        } catch (RestClientException e) {
            log.error("Ollama 식단 파싱 호출 실패", e);
            throw new ExternalServiceException("식단 인식 서버에 연결할 수 없어요. 잠시 후 다시 시도해주세요.", e);
        }
 
        return parseResponse(responseJson);
    }
 
    private String expandSlang(String rawMessage) {
        String result = rawMessage;
        for (Map.Entry<String, String> alias : SLANG_ALIASES.entrySet()) {
            result = result.replace(alias.getKey(), alias.getValue());
        }
        return result;
    }

    private List<FoodItem> parseResponse(String responseJson) {
        String modelText = null;
        try {
            JsonNode root = objectMapper.readTree(responseJson);
            modelText = root.path("message").path("content").asText();
 
            // format:"json"을 요청하면 대부분 순수 JSON만 오지만, 혹시 모를 코드블록 래핑에 대비해 유지
            String cleaned = modelText.trim()
                    .replaceAll("^```json\\s*", "")
                    .replaceAll("^```\\s*", "")
                    .replaceAll("```\\s*$", "")
                    .trim();

            // Ollama의 format:"json"은 최상위를 객체로만 허용해서(배열을 바로 못 줌) items 키로 감싸서 받음.
            // 이걸 놓치면 모델이 배열 대신 객체 하나만 반환하고, 그 객체를 배열처럼 순회하면서
            // foodName이 전부 비어 조회 실패(못 찾음) 처리되는 문제로 이어짐.
            JsonNode itemsArray = objectMapper.readTree(cleaned).path("items");
            List<FoodItem> items = new ArrayList<>();
            for (JsonNode item : itemsArray) {
                String name = item.path("foodName").asText();
                String searchName = item.path("searchName").asText("");
                JsonNode amountNode = item.path("amountG");
                Double amountG = (amountNode.isMissingNode() || amountNode.isNull()) ? null : amountNode.asDouble();
                double servings = item.path("servings").asDouble(1.0);
                if (servings <= 0) {
                    servings = 1.0;
                }
                items.add(new FoodItem(name, searchName.isBlank() ? name : searchName, amountG, servings));
            }
            return items;
        } catch (Exception e) {
            // 모델 원문은 사용자에게 노출하지 않고 로그에만 남김 (내부 정보 유출 방지)
            log.error("Qwen 식단 파싱 응답 처리 실패. 모델 원문: {}", modelText, e);
            throw new ExternalServiceException("식사 내용을 이해하지 못했어요. 다른 표현으로 다시 시도해주세요.", e);
        }
    }

    /**
     * foodName: 기록에 남기는 이름 (사용자가 말한 그대로, 예: "포카칩 큰 봉지")
     * searchName: DB 검색에 쓰는 기본 제품명 (용량 표현 제거, 예: "포카칩")
     * amountG: 사용자가 그램/ml을 직접 말했을 때만 값이 있음(null이면 미지정) - 있으면 이 값을 그대로 씀
     * servings: 인분수/개수 (amountG가 null일 때만 의미 있음) - DB 표준중량과 곱해서 그램 환산
     */
    public record FoodItem(String foodName, String searchName, Double amountG, double servings) {}
}
 
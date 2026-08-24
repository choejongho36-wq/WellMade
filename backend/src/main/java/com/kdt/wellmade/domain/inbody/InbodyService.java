package com.kdt.wellmade.domain.inbody;

import java.io.IOException;
import java.util.Base64;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.multipart.MultipartFile;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.kdt.wellmade.domain.user.User;


    

 /* Gemini API(무료 티어, 비전 지원)로 인바디 사진에서 바로 구조화된 값을 추출하는 서비스.
 */
@Service
public class InbodyService {
 
    private static final String ENDPOINT_TEMPLATE =
            "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent";
 
    private static final String PROMPT = """
            이 이미지는 InBody 체성분 분석 결과지입니다. 아래 값을 정확히 읽어서 JSON으로만 답하세요.
            다른 설명이나 마크다운 코드블록 없이 순수 JSON 객체 하나만 출력하세요.
 
           읽을 값 (라벨이 비슷해서 헷갈리지 않도록 주의하세요):
            - weightKg: 체중 (kg). "신체변화" 이력 표가 있다면 그중 가장 최근(마지막) 값을 우선하세요.
            - skeletalMuscleMassKg: "골격근량" (Skeletal Muscle Mass, kg). "근육량"(총 근육량)과는 다른 값이니 혼동하지 마세요.
            - bodyFatPercentage: "체지방률" (Percent Body Fat, %). "체지방량"(kg 단위)과 다른 값이니 혼동하지 마세요.
            - basalMetabolicRateKcal: 기초대사량 (kcal)
            - bmi: BMI (Body Mass Index), "비만분석" 섹션에 있는 값

            해당 값을 이미지에서 찾을 수 없으면 그 필드는 null로 두세요.

            출력 형식 예시:
            {"weightKg": 89.5, "skeletalMuscleMassKg": 34.3, "bodyFatPercentage": 31.7, "basalMetabolicRateKcal": 1691, "bmi": 26.7}
            """;
 
    private final String apiKey;
    private final String model;
    private final InbodyRecordRepository inbodyRecordRepository;
    private final RestTemplate restTemplate = new RestTemplate();
    private final ObjectMapper objectMapper = new ObjectMapper();

    public InbodyService(
            @Value("${gemini.api-key}") String apiKey,
            @Value("${gemini.model}") String model,
            InbodyRecordRepository inbodyRecordRepository
    ) {
        this.apiKey = apiKey;
        this.model = model;
        this.inbodyRecordRepository = inbodyRecordRepository;
    }

    @Transactional
    public InbodyRecord save(User user, InbodyConfirmRequest request) {
        InbodyRecord record = InbodyRecord.builder()
                .user(user)
                .weightKg(request.weightKg())
                .skeletalMuscleMassKg(request.skeletalMuscleMassKg())
                .bodyFatPercentage(request.bodyFatPercentage())
                .basalMetabolicRateKcal(request.basalMetabolicRateKcal())
                .bmi(request.bmi())
                .build();
        return inbodyRecordRepository.save(record);
    }

    @Transactional(readOnly = true)
    public Optional<InbodyRecord> getLatest(User user) {
        return inbodyRecordRepository.findTopByUserOrderByCreatedAtDesc(user);
    }

    public InbodyResult extract(MultipartFile imageFile) throws IOException {
        String base64Image = Base64.getEncoder().encodeToString(imageFile.getBytes());
        String mimeType = imageFile.getContentType() != null ? imageFile.getContentType() : "image/jpeg";
 
        Map<String, Object> requestBody = Map.of(
                "contents", List.of(
                        Map.of("parts", List.of(
                                Map.of("text", PROMPT),
                                Map.of("inline_data", Map.of(
                                        "mime_type", mimeType,
                                        "data", base64Image
                                ))
                        ))
                )
        );
 
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.set("x-goog-api-key", apiKey);
 
        String url = String.format(ENDPOINT_TEMPLATE, model);
        HttpEntity<Map<String, Object>> request = new HttpEntity<>(requestBody, headers);
 
        String responseJson = restTemplate.postForObject(url, request, String.class);
        return parseResponse(responseJson);
    }
 
    private InbodyResult parseResponse(String responseJson) throws IOException {
        JsonNode root = objectMapper.readTree(responseJson);

        JsonNode candidates = root.path("candidates");
        if (!candidates.isArray() || candidates.isEmpty()) {
            String blockReason = root.path("promptFeedback").path("blockReason").asText("알 수 없음");
            throw new IOException("Gemini가 이미지를 처리하지 못했습니다 (사유: " + blockReason + ")");
        }

        String modelText = candidates.get(0)
                .path("content").path("parts").get(0)
                .path("text").asText();
 
        // 혹시 모델이 ```json 코드블록으로 감싸서 응답하면 벗겨내기
        String cleaned = modelText.trim()
                .replaceAll("^```json\\s*", "")
                .replaceAll("^```\\s*", "")
                .replaceAll("```\\s*$", "")
                .trim();
 
        JsonNode fields = objectMapper.readTree(cleaned);
 
        Double weight = fields.hasNonNull("weightKg") ? fields.get("weightKg").asDouble() : null;
        Double muscle = fields.hasNonNull("skeletalMuscleMassKg") ? fields.get("skeletalMuscleMassKg").asDouble() : null;
        Double fatPct = fields.hasNonNull("bodyFatPercentage") ? fields.get("bodyFatPercentage").asDouble() : null;
        Integer bmr = fields.hasNonNull("basalMetabolicRateKcal") ? fields.get("basalMetabolicRateKcal").asInt() : null;
        Double bmi = fields.hasNonNull("bmi") ? fields.get("bmi").asDouble() : null;

        return new InbodyResult(weight, muscle, fatPct, bmr, bmi, cleaned);
    }
}


package com.kdt.wellmade.domain.chat;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import com.kdt.wellmade.domain.inbody.InbodyRecord;
import com.kdt.wellmade.domain.inbody.InbodyService;
import com.kdt.wellmade.domain.mapage.Goal;
import com.kdt.wellmade.domain.mapage.UserProfile;
import com.kdt.wellmade.domain.mapage.UserProfileService;
import com.kdt.wellmade.domain.user.User;

/* 로컬 Ollama(Qwen2.5-7B-Instruct)에 사용자의 goal/인바디 값을 시스템 프롬프트로 얹어 채팅을 중계하는 서비스.
 */
@Service
public class ChatService {

    private static final String SYSTEM_PROMPT =
            "당신은 인바디 측정 수치와 사용자 목표를 바탕으로 식단과 운동을 추천하는 헬스케어 AI 어시스턴트입니다. "
          + "의학적 진단이 아닌 생활습관 조언을 제공하며, 친근하고 구체적인 톤으로 답변합니다. "
          + "마크다운 헤더나 표, 이모지 없이 대화체 문장으로 간결하게 답변합니다.";

    private static final Map<Goal, String> GOAL_LABEL = Map.of(
            Goal.LOSE, "체중감량",
            Goal.GAIN, "근성장(벌크업)",
            Goal.MAINTAIN, "체형 유지/건강관리"
    );

    private final UserProfileService userProfileService;
    private final InbodyService inbodyService;
    private final RestTemplate restTemplate = new RestTemplate();
    private final String baseUrl;
    private final String model;

    public ChatService(
            UserProfileService userProfileService,
            InbodyService inbodyService,
            @Value("${ollama.base-url}") String baseUrl,
            @Value("${ollama.model}") String model
    ) {
        this.userProfileService = userProfileService;
        this.inbodyService = inbodyService;
        this.baseUrl = baseUrl;
        this.model = model;
    }

    public String reply(User user, List<ChatMessage> conversation) {
        List<ChatMessage> messages = new ArrayList<>();
        messages.add(new ChatMessage("system", buildSystemPrompt(user)));
        messages.addAll(conversation);

        Map<String, Object> requestBody = Map.of(
                "model", model,
                "stream", false,
                "messages", messages
        );

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        HttpEntity<Map<String, Object>> request = new HttpEntity<>(requestBody, headers);

        OllamaChatResponse response = restTemplate.postForObject(
                baseUrl + "/api/chat", request, OllamaChatResponse.class);

        if (response == null || response.message() == null) {
            throw new IllegalStateException("Qwen 응답을 받지 못했습니다.");
        }
        return response.message().content();
    }

    private String buildSystemPrompt(User user) {
        UserProfile profile = getProfileOrNull(user);
        InbodyRecord inbody = inbodyService.getLatest(user).orElse(null);

        boolean hasGoal = profile != null && profile.getGoal() != null;
        if (!hasGoal && inbody == null) {
            return SYSTEM_PROMPT;
        }

        StringBuilder sb = new StringBuilder(SYSTEM_PROMPT).append("\n\n사용자 정보:");
        if (hasGoal) {
            sb.append("\n- 목표: ").append(GOAL_LABEL.get(profile.getGoal()));
        }
        if (inbody != null) {
            List<String> parts = new ArrayList<>();
            if (inbody.getWeightKg() != null) parts.add("체중 " + inbody.getWeightKg() + "kg");
            if (inbody.getSkeletalMuscleMassKg() != null) parts.add("골격근량 " + inbody.getSkeletalMuscleMassKg() + "kg");
            if (inbody.getBodyFatPercentage() != null) parts.add("체지방률 " + inbody.getBodyFatPercentage() + "%");
            if (!parts.isEmpty()) {
                sb.append("\n- 최근 측정한 인바디 수치: ").append(String.join(", ", parts));
            }
            if (inbody.getBasalMetabolicRateKcal() != null) {
                sb.append("\n- 기초대사량: ").append(inbody.getBasalMetabolicRateKcal()).append("kcal");
            }
        }
        return sb.toString();
    }

    private UserProfile getProfileOrNull(User user) {
        try {
            return userProfileService.getProfile(user);
        } catch (IllegalArgumentException e) {
            return null;
        }
    }

    private record OllamaChatResponse(ChatMessage message) {
    }
}

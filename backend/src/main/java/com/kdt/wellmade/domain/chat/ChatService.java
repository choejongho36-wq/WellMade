package com.kdt.wellmade.domain.chat;

import java.time.LocalDate;
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
import com.kdt.wellmade.domain.nutrition.MealLoggingService;
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
    private final MealLoggingService mealLoggingService;
    private final RestTemplate restTemplate = new RestTemplate();
    private final String baseUrl;
    private final String model;

    public ChatService(
            UserProfileService userProfileService,
            InbodyService inbodyService,
            MealLoggingService mealLoggingService,
            @Value("${ollama.base-url}") String baseUrl,
            @Value("${ollama.model}") String model
    ) {
        this.userProfileService = userProfileService;
        this.inbodyService = inbodyService;
        this.mealLoggingService = mealLoggingService;
        this.baseUrl = baseUrl;
        this.model = model;
    }

    public String reply(User user, List<ChatMessage> conversation) {
        List<ChatMessage> messages = new ArrayList<>();
        messages.add(new ChatMessage("system", buildSystemPrompt(user)));
        messages.addAll(conversation);
        return callOllama(messages);
    }

    /**
     * 인바디+목표로 계산한 목표 영양소와 오늘 실제 섭취량을 비교해서 LLM이 조언하게 함.
     * 계산(목표치 산출, 차이 비교)은 전부 결정론적 수식이고, LLM은 그 결과를 자연어로 풀어주는 역할만 함.
     */
    public String nutrientAdvice(User user, Long userId) {
        InbodyRecord inbody = inbodyService.getLatest(user).orElse(null);
        if (inbody == null || inbody.getWeightKg() == null) {
            return "인바디 정보가 없어서 분석할 수 없어요. 마이페이지에서 인바디를 먼저 등록해주세요.";
        }

        UserProfile profile = getProfileOrNull(user);
        if (profile == null || profile.getGoal() == null) {
            return "목표가 설정되어 있지 않아요. 마이페이지에서 목표(체중감량/근육증가/체중유지)를 먼저 설정해주세요.";
        }

        MealLoggingService.DailyTotal actual = mealLoggingService.getTotalForDate(userId, LocalDate.now());
        if (actual.mealCount() == 0) {
            return "오늘 기록된 식사가 아직 없어요. 식단을 기록하면 목표 대비 분석해드릴게요.";
        }

        Goal goal = profile.getGoal();
        NutrientTarget target = calculateTarget(inbody, goal);

        List<ChatMessage> messages = new ArrayList<>();
        messages.add(new ChatMessage("system", buildSystemPrompt(user) + "\n\n" + buildAdviceContext(goal, target, actual)));
        messages.add(new ChatMessage("user", "오늘 내가 먹은 식단이 목표 대비 어떤지 분석해서 부족하거나 초과된 영양소를 짚어주고 조언해줘."));
        return callOllama(messages);
    }

    private String callOllama(List<ChatMessage> messages) {
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

    /** ponytail: 활동계수 1.375(가벼운 활동) 고정값, 기초대사량 없으면 체중×24로 대략 추정 - 활동량 입력 받으면 그걸로 교체 */
    private NutrientTarget calculateTarget(InbodyRecord inbody, Goal goal) {
        double weight = inbody.getWeightKg();
        double bmr = inbody.getBasalMetabolicRateKcal() != null ? inbody.getBasalMetabolicRateKcal() : weight * 24;
        double tdee = bmr * 1.375;

        double targetKcal = switch (goal) {
            case LOSE -> tdee * 0.85;
            case GAIN -> tdee * 1.15;
            case MAINTAIN -> tdee;
        };
        double proteinPerKg = switch (goal) {
            case LOSE -> 1.8;
            case GAIN -> 2.0;
            case MAINTAIN -> 1.4;
        };
        double targetProtein = weight * proteinPerKg;
        double targetFat = targetKcal * 0.25 / 9;
        double targetCarbs = Math.max(0, (targetKcal - targetProtein * 4 - targetFat * 9) / 4);

        return new NutrientTarget(targetKcal, targetProtein, targetCarbs, targetFat);
    }

    private String buildAdviceContext(Goal goal, NutrientTarget target, MealLoggingService.DailyTotal actual) {
        return """
                [오늘 영양소 분석 요청 - 아래 수치는 이미 계산된 값이니 그대로 인용해서 설명할 것]
                목표: %s
                목표 섭취량 - 칼로리: %.0fkcal, 단백질: %.0fg, 탄수화물: %.0fg, 지방: %.0fg
                오늘 실제 섭취량 - 칼로리: %.0fkcal, 단백질: %.1fg, 탄수화물: %.1fg, 지방: %.1fg
                """.formatted(
                GOAL_LABEL.get(goal),
                target.kcal(), target.proteinG(), target.carbsG(), target.fatG(),
                actual.totalCalories(), actual.totalProteinG(), actual.totalCarbsG(), actual.totalFatG()
        );
    }

    private record NutrientTarget(double kcal, double proteinG, double carbsG, double fatG) {}

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

package com.kdt.wellmade.domain.chat;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.kdt.wellmade.domain.inbody.InbodyRecord;
import com.kdt.wellmade.domain.inbody.InbodyService;
import com.kdt.wellmade.domain.mapage.Gender;
import com.kdt.wellmade.domain.mapage.Goal;
import com.kdt.wellmade.domain.mapage.UserProfile;
import com.kdt.wellmade.domain.mapage.UserProfileService;
import com.kdt.wellmade.domain.nutrition.MealLoggingService;
import com.kdt.wellmade.domain.nutrition.NutrientTarget;
import com.kdt.wellmade.domain.nutrition.NutrientTargetCalculator;
import com.kdt.wellmade.domain.user.User;
import com.kdt.wellmade.global.exception.ExternalServiceException;

/**
 * 로컬 Ollama(Qwen2.5-7B-Instruct)에 사용자의 goal/인바디 값을 시스템 프롬프트로 얹어 채팅을 중계하는 서비스.
 *
 * 대화 이력은 이제 DB(chat_messages)가 진실 소스임. 예전엔 프론트가 매 요청마다 전체 대화 배열을
 * 그대로 보내고 서버는 그걸 신뢰하는 구조였어서, role을 위조한 메시지를 끼워넣을 수 있었고
 * 새로고침하면 이력이 통째로 사라졌음. 이제 클라이언트는 새로 보낸 사용자 메시지 하나만 전달하고,
 * 서버가 최근 이력을 불러와 컨텍스트를 구성한 뒤 이번 턴(사용자+응답)을 저장함.
 *
 * 일반 채팅(reply)은 툴콜링을 지원함 - 모델이 "어제 뭐 먹었지?" 같은 질문에 스스로 get_meals_for_date
 * 도구를 호출해서 실제 DB 값을 확인한 뒤 답하게 함. 계산이 필요한 질문(목표 섭취량 등)도 마찬가지로
 * calculate_nutrient_target 도구가 계산한 결정론적 수치를 인용하게 하고, 모델이 암산하지 않게 함.
 * nutrientAdvice()는 원래도 계산을 서버가 다 해서 프롬프트에 박아넣는 방식이라 툴콜링이 필요 없어서 그대로 둠.
 */
@Service
public class ChatService {

    private static final Logger log = LoggerFactory.getLogger(ChatService.class);

    // Ollama에 보낼 컨텍스트로 불러올 최근 이력 개수 (너무 많으면 num_ctx를 넘겨서 앞부분이 잘림)
    private static final int CONTEXT_HISTORY_LIMIT = 30;
    // 프론트에 "이전 대화 이어서 보기"용으로 내려줄 이력 개수
    private static final int DISPLAY_HISTORY_LIMIT = 100;
    private static final int MAX_CONTENT_LENGTH = 2000;

    // 모델이 도구 호출을 계속 이어가며 끝내지 않는 경우를 대비한 상한.
    // 이 라운드를 다 쓰면 마지막엔 tools 없이 강제로 마무리 답변을 받음.
    private static final int MAX_TOOL_ROUNDS = 3;

    private static final String SYSTEM_PROMPT =
            "당신은 인바디 측정 수치와 사용자 목표를 바탕으로 식단과 운동을 추천하는 헬스케어 AI 어시스턴트입니다. "
          + "의학적 진단이 아닌 생활습관 조언을 제공하며, 친근하고 구체적인 톤으로 답변합니다. "
          + "마크다운 헤더나 표, 이모지 없이 대화체 문장으로 간결하게 답변합니다. "
          + "식사 기록, 섭취량, 목표 섭취량처럼 실제 데이터가 필요한 질문에는 절대 추측하거나 암산하지 말고, "
          + "제공된 도구를 호출해서 실제 값을 확인한 뒤에 그 값을 인용해서 답변하세요.";

    private static final Map<Goal, String> GOAL_LABEL = Map.of(
            Goal.LOSE, "체중감량",
            Goal.GAIN, "근성장(벌크업)",
            Goal.MAINTAIN, "체형 유지/건강관리"
    );

    /** Ollama에 넘길 도구 스펙 (OpenAI function-calling 호환 형식). Qwen2.5-Instruct가 이 형식을 지원함. */
    private static final List<Map<String, Object>> TOOLS = List.of(
            toolDef(
                    "get_meals_for_date",
                    "특정 날짜에 사용자가 기록한 식사 목록(끼니 종류, 메뉴명, 칼로리)을 가져온다. "
                  + "'어제 뭐 먹었지', '오늘 아침에 뭐 먹었더라' 같은 질문에는 반드시 이 도구로 실제 기록을 "
                  + "확인하고 답할 것 - 절대 추측하지 말 것.",
                    Map.of("date", Map.of(
                            "type", "string",
                            "description", "조회할 날짜, yyyy-MM-dd 형식. '어제'/'오늘'처럼 상대적인 표현은 "
                                    + "시스템 프롬프트에 적힌 오늘 날짜를 기준으로 직접 계산해서 넣을 것."
                    )),
                    List.of("date")
            ),
            toolDef(
                    "get_daily_total",
                    "특정 날짜의 총 섭취 칼로리/단백질/탄수화물/지방 합계를 가져온다.",
                    Map.of("date", Map.of(
                            "type", "string",
                            "description", "조회할 날짜, yyyy-MM-dd 형식."
                    )),
                    List.of("date")
            ),
            toolDef(
                    "get_inbody_history",
                    "최근 인바디 측정 기록을 오래된 순으로 여러 건 가져온다(체중/골격근량/체지방률/BMI). "
                  + "'요즘 체중 변화 어때', '살 빠지고 있어?'처럼 추세를 물어볼 때 인바디 한 건(최신값)만으로 "
                  + "답하지 말고 이 도구로 여러 건을 확인할 것.",
                    Map.of("limit", Map.of(
                            "type", "integer",
                            "description", "가져올 기록 개수. 생략하면 5, 최대 10."
                    )),
                    List.of()
            ),
            toolDef(
                    "calculate_nutrient_target",
                    "사용자의 목표와 최근 인바디 수치를 바탕으로 하루 목표 칼로리/단백질/탄수화물/지방을 "
                  + "계산한다. 목표 섭취량을 묻는 질문에는 반드시 이 도구로 계산된 값을 인용할 것 - 직접 "
                  + "암산하지 말 것.",
                    Map.of(),
                    List.of()
            )
    );

    private final UserProfileService userProfileService;
    private final InbodyService inbodyService;
    private final MealLoggingService mealLoggingService;
    private final ChatMessageRepository chatMessageRepository;
    private final NutrientTargetCalculator nutrientTargetCalculator;
    private final RestClient ollamaRestClient;
    private final String model;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public ChatService(
            UserProfileService userProfileService,
            InbodyService inbodyService,
            MealLoggingService mealLoggingService,
            ChatMessageRepository chatMessageRepository,
            NutrientTargetCalculator nutrientTargetCalculator,
            RestClient ollamaRestClient,
            @Value("${ollama.model}") String model
    ) {
        this.userProfileService = userProfileService;
        this.inbodyService = inbodyService;
        this.mealLoggingService = mealLoggingService;
        this.chatMessageRepository = chatMessageRepository;
        this.nutrientTargetCalculator = nutrientTargetCalculator;
        this.ollamaRestClient = ollamaRestClient;
        this.model = model;
    }

    /**
     * 새 사용자 메시지 하나를 받아서, DB에 저장된 최근 이력 + 이번 메시지로 컨텍스트를 구성하고
     * 응답을 받은 뒤 이번 턴(사용자 메시지 + 어시스턴트 응답)을 저장함.
     */
    public String reply(User user, String rawMessage) {
        String userMessage = validateAndTrim(rawMessage);

        List<OllamaMessage> messages = new ArrayList<>();
        messages.add(OllamaMessage.system(buildSystemPrompt(user)));
        for (ChatMessageEntity h : loadRecentHistory(user, CONTEXT_HISTORY_LIMIT)) {
            messages.add(new OllamaMessage(h.getRole(), h.getContent(), null, null));
        }
        messages.add(OllamaMessage.user(userMessage));

        String reply = converseWithTools(user, messages);

        // Ollama 호출(느릴 수 있음)이 끝난 뒤에 저장함 - 트랜잭션을 외부 HTTP 호출 동안 붙잡고
        // 있지 않으려는 의도. 두 저장 사이에 실패가 나도 사용자 메시지 한 줄만 남는 정도라 치명적이지 않음.
        chatMessageRepository.save(ChatMessageEntity.builder().user(user).role("user").content(userMessage).build());
        chatMessageRepository.save(ChatMessageEntity.builder().user(user).role("assistant").content(reply).build());

        return reply;
    }

    /** 프론트에서 드로어를 열 때 "이전 대화 이어보기"용으로 내려줄 이력 (오래된 순) */
    public List<ChatHistoryItem> getHistory(User user) {
        return loadRecentHistory(user, DISPLAY_HISTORY_LIMIT).stream()
                .map(h -> new ChatHistoryItem(h.getRole(), h.getContent(), h.getCreatedAt()))
                .toList();
    }

    /** 최신순으로 limit건 가져온 뒤 시간순으로 뒤집어서 반환 */
    private List<ChatMessageEntity> loadRecentHistory(User user, int limit) {
        List<ChatMessageEntity> recentFirst =
                chatMessageRepository.findByUserOrderByCreatedAtDesc(user, PageRequest.of(0, limit));
        List<ChatMessageEntity> chronological = new ArrayList<>(recentFirst);
        Collections.reverse(chronological);
        return chronological;
    }

    /** 빈 메시지 거부 + 길이 상한. 예전엔 클라이언트가 배열 통째로 보내서 role 위조가 가능했지만,
     *  이제 문자열 하나만 받으므로 검증할 것도 이 정도로 단순해짐. */
    private String validateAndTrim(String rawMessage) {
        if (rawMessage == null || rawMessage.isBlank()) {
            throw new IllegalArgumentException("메시지를 입력해주세요.");
        }
        String trimmed = rawMessage.trim();
        return trimmed.length() > MAX_CONTENT_LENGTH ? trimmed.substring(0, MAX_CONTENT_LENGTH) : trimmed;
    }

    /**
     * 모델이 도구 호출을 요청하면 실행하고 결과를 대화에 이어붙여서 다시 물어보는 루프.
     * 도구 호출이 없는 응답이 오면 그게 최종 답변.
     */
    private String converseWithTools(User user, List<OllamaMessage> messages) {
        for (int round = 0; round < MAX_TOOL_ROUNDS; round++) {
            OllamaMessage assistantMsg = chatCompletion(messages, true);

            if (assistantMsg.tool_calls() == null || assistantMsg.tool_calls().isEmpty()) {
                return assistantMsg.content();
            }

            messages.add(assistantMsg);
            for (OllamaMessage.ToolCall call : assistantMsg.tool_calls()) {
                String result = executeTool(user, call.function().name(), call.function().arguments());
                messages.add(OllamaMessage.tool(result, call.id()));
            }
        }

        // 라운드를 다 썼는데도 계속 도구를 부르면, 이번엔 tools 없이 마지막으로 한 번 더 요청해서
        // 지금까지 모은 도구 결과만으로라도 답변을 강제로 마무리시킴 (무한 루프 방지).
        log.warn("도구 호출이 {}라운드를 초과해서 강제로 마무리함. userId={}", MAX_TOOL_ROUNDS, user.getId());
        OllamaMessage finalMsg = chatCompletion(messages, false);
        return finalMsg.content() != null && !finalMsg.content().isBlank()
                ? finalMsg.content()
                : "요청하신 내용을 정리하는 데 문제가 있었어요. 다시 한 번 물어봐 주세요.";
    }

    private String executeTool(User user, String name, Map<String, Object> arguments) {
        try {
            return switch (name) {
                case "get_meals_for_date" -> toolGetMealsForDate(user.getId(), arguments);
                case "get_daily_total" -> toolGetDailyTotal(user.getId(), arguments);
                case "get_inbody_history" -> toolGetInbodyHistory(user, arguments);
                case "calculate_nutrient_target" -> toolCalculateNutrientTarget(user);
                default -> toJson(Map.of("error", "알 수 없는 도구입니다: " + name));
            };
        } catch (Exception e) {
            log.error("도구 실행 실패: {}", name, e);
            return toJson(Map.of("error", "도구 실행 중 문제가 발생했어요."));
        }
    }

    private String toolGetMealsForDate(Long userId, Map<String, Object> args) {
        LocalDate date = parseDateArgOrToday(args);
        List<Map<String, Object>> meals = mealLoggingService.getMealsForDate(userId, date);

        List<Map<String, Object>> simplified = meals.stream()
                .map(m -> Map.<String, Object>of(
                        "mealType", String.valueOf(m.get("meal_type")),
                        "menuName", String.valueOf(m.get("menu_name")),
                        "kcal", m.get("kcal")
                ))
                .toList();

        return toJson(Map.of("date", date.toString(), "meals", simplified));
    }

    private String toolGetDailyTotal(Long userId, Map<String, Object> args) {
        LocalDate date = parseDateArgOrToday(args);
        MealLoggingService.DailyTotal total = mealLoggingService.getTotalForDate(userId, date);

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("date", date.toString());
        result.put("totalCalories", total.totalCalories());
        result.put("totalProteinG", total.totalProteinG());
        result.put("totalCarbsG", total.totalCarbsG());
        result.put("totalFatG", total.totalFatG());
        result.put("mealCount", total.mealCount());
        return toJson(result);
    }

    private String toolGetInbodyHistory(User user, Map<String, Object> args) {
        int limit = argInt(args, "limit", 5);
        List<InbodyRecord> history = inbodyService.getHistory(user, limit);

        if (history.isEmpty()) {
            return toJson(Map.of("records", List.of(), "note", "등록된 인바디 기록이 없어요."));
        }

        List<Map<String, Object>> records = history.stream()
                // 최신순으로 조회되므로, 추세를 시간 순서대로 읽기 쉽게 오래된 것부터 정렬해서 돌려줌
                .sorted(Comparator.comparing(InbodyRecord::getCreatedAt))
                .map(r -> {
                    Map<String, Object> m = new LinkedHashMap<>();
                    m.put("date", r.getCreatedAt().toLocalDate().toString());
                    m.put("weightKg", r.getWeightKg());
                    m.put("skeletalMuscleMassKg", r.getSkeletalMuscleMassKg());
                    m.put("bodyFatPercentage", r.getBodyFatPercentage());
                    m.put("bmi", r.getBmi());
                    return m;
                })
                .toList();

        return toJson(Map.of("records", records));
    }

    private String toolCalculateNutrientTarget(User user) {
        UserProfile profile = getProfileOrNull(user);
        if (profile == null || profile.getGoal() == null) {
            return toJson(Map.of("error", "목표가 설정되어 있지 않아요. 마이페이지에서 목표를 먼저 설정해야 계산할 수 있어요."));
        }

        InbodyRecord inbody = inbodyService.getLatest(user).orElse(null);
        if (inbody == null || inbody.getWeightKg() == null) {
            return toJson(Map.of("error", "인바디 정보가 없어서 목표 섭취량을 계산할 수 없어요."));
        }

        NutrientTarget target = nutrientTargetCalculator.calculate(inbody, profile);

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("goal", GOAL_LABEL.get(profile.getGoal()));
        result.put("targetKcal", Math.round(target.kcal()));
        result.put("targetProteinG", Math.round(target.proteinG()));
        result.put("targetCarbsG", Math.round(target.carbsG()));
        result.put("targetFatG", Math.round(target.fatG()));
        return toJson(result);
    }

    private LocalDate parseDateArgOrToday(Map<String, Object> args) {
        String raw = argString(args, "date", null);
        if (raw == null) {
            return LocalDate.now();
        }
        try {
            return LocalDate.parse(raw);
        } catch (Exception e) {
            // 모델이 날짜 형식을 잘못 넣으면(예: "어제"를 계산 안 하고 그대로 보냄) 오늘로 대체.
            // 여기서 예외를 던지면 도구 호출 자체가 실패해서 답변을 아예 못 받는 게 더 나쁨.
            log.warn("도구 호출의 date 인자를 파싱하지 못해 오늘 날짜로 대체함: {}", raw);
            return LocalDate.now();
        }
    }

    private String argString(Map<String, Object> args, String key, String defaultVal) {
        Object v = args == null ? null : args.get(key);
        return v != null ? String.valueOf(v) : defaultVal;
    }

    private int argInt(Map<String, Object> args, String key, int defaultVal) {
        Object v = args == null ? null : args.get(key);
        if (v instanceof Number n) return n.intValue();
        if (v instanceof String s) {
            try {
                return Integer.parseInt(s.trim());
            } catch (NumberFormatException e) {
                return defaultVal;
            }
        }
        return defaultVal;
    }

    /**
     * 인바디+목표로 계산한 목표 영양소와 오늘 실제 섭취량을 비교해서 LLM이 조언하게 함.
     * 계산(목표치 산출, 차이 비교)은 전부 결정론적 수식이고, LLM은 그 결과를 자연어로 풀어주는 역할만 함.
     * 필요한 데이터를 이미 프롬프트에 다 박아넣기 때문에 툴콜링은 쓰지 않음.
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
        NutrientTarget target = nutrientTargetCalculator.calculate(inbody, profile);

        List<OllamaMessage> messages = new ArrayList<>();
        messages.add(OllamaMessage.system(buildSystemPrompt(user) + "\n\n" + buildAdviceContext(goal, target, actual)));
        String userLabel = "오늘 내가 먹은 식단이 목표 대비 어떤지 분석해서 부족하거나 초과된 영양소를 짚어주고 조언해줘.";
        messages.add(OllamaMessage.user(userLabel));
        String reply = chatCompletion(messages, false).content();

        // 이 흐름도 같은 대화창(ChatDrawer)에 이어서 보여지므로, 새로고침 후에도 이어지도록 이력에 남김
        chatMessageRepository.save(ChatMessageEntity.builder().user(user).role("user").content(userLabel).build());
        chatMessageRepository.save(ChatMessageEntity.builder().user(user).role("assistant").content(reply).build());

        return reply;
    }

    private OllamaMessage chatCompletion(List<OllamaMessage> messages, boolean includeTools) {
        Map<String, Object> requestBody = new LinkedHashMap<>();
        requestBody.put("model", model);
        requestBody.put("stream", false);
        requestBody.put("messages", messages);
        // temperature 미지정 시 Ollama 기본값(0.8)이 적용되던 걸 명시적으로 낮춤.
        // num_ctx를 안 주면 대화가 길어질 때 앞부분(시스템 프롬프트=인바디 수치 등)이
        // 조용히 잘려나갈 수 있어서 같이 지정.
        requestBody.put("options", Map.of(
                "temperature", 0.4,
                "num_ctx", 8192,
                "num_predict", 512
        ));
        if (includeTools) {
            requestBody.put("tools", TOOLS);
        }

        OllamaChatResponse response;
        try {
            response = ollamaRestClient.post()
                    .uri("/api/chat")
                    .body(requestBody)
                    .retrieve()
                    .body(OllamaChatResponse.class);
        } catch (RestClientException e) {
            // 원인(연결 실패/타임아웃 등)은 로그에만 남기고, 사용자에게는 안전한 메시지만 노출
            log.error("Ollama 채팅 호출 실패", e);
            throw new ExternalServiceException("지금은 챗봇 응답을 받을 수 없어요. 잠시 후 다시 시도해주세요.", e);
        }

        if (response == null || response.message() == null) {
            log.error("Ollama 채팅 응답이 비어있습니다.");
            throw new ExternalServiceException("지금은 챗봇 응답을 받을 수 없어요. 잠시 후 다시 시도해주세요.");
        }
        return response.message();
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

    private String buildSystemPrompt(User user) {
        UserProfile profile = getProfileOrNull(user);
        InbodyRecord inbody = inbodyService.getLatest(user).orElse(null);

        StringBuilder sb = new StringBuilder(SYSTEM_PROMPT)
                .append("\n\n오늘 날짜: ").append(LocalDate.now())
                .append(" (사용자가 '어제', '이번 주'처럼 상대적으로 말하면 이 날짜를 기준으로 계산해서 도구를 호출할 것)");

        boolean hasGoal = profile != null && profile.getGoal() != null;
        if (!hasGoal && inbody == null) {
            return sb.toString();
        }

        sb.append("\n\n사용자 정보:");
        if (hasGoal) {
            sb.append("\n- 목표: ").append(GOAL_LABEL.get(profile.getGoal()));
        }
        // 체지방률 정상범위·권장 섭취량이 성별에 따라 다르므로 모델에게 같이 알려줌
        if (profile != null) {
            List<String> body = new ArrayList<>();
            if (profile.getGender() != null) body.add(profile.getGender() == Gender.MALE ? "남성" : "여성");
            if (profile.getHeightCm() != null) body.add("키 " + profile.getHeightCm() + "cm");
            if (profile.getBirthYear() != null) body.add("만 " + (LocalDate.now().getYear() - profile.getBirthYear()) + "세");
            if (!body.isEmpty()) {
                sb.append("\n- 신체 정보: ").append(String.join(", ", body));
            }
        }
        if (inbody != null) {
            List<String> parts = new ArrayList<>();
            if (inbody.getWeightKg() != null) parts.add("체중 " + inbody.getWeightKg() + "kg");
            if (inbody.getSkeletalMuscleMassKg() != null) parts.add("골격근량 " + inbody.getSkeletalMuscleMassKg() + "kg");
            if (inbody.getBodyFatPercentage() != null) parts.add("체지방률 " + inbody.getBodyFatPercentage() + "%");
            if (!parts.isEmpty()) {
                sb.append("\n- 최근 측정한 인바디 수치(1건, 추세는 get_inbody_history 도구로 확인): ").append(String.join(", ", parts));
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

    private String toJson(Object obj) {
        try {
            return objectMapper.writeValueAsString(obj);
        } catch (Exception e) {
            log.error("도구 결과 직렬화 실패", e);
            return "{\"error\": \"결과를 표현하는 중 문제가 발생했어요.\"}";
        }
    }

    private static Map<String, Object> toolDef(
            String name, String description, Map<String, Object> properties, List<String> required
    ) {
        Map<String, Object> parameters = new LinkedHashMap<>();
        parameters.put("type", "object");
        parameters.put("properties", properties);
        parameters.put("required", required);

        Map<String, Object> function = new LinkedHashMap<>();
        function.put("name", name);
        function.put("description", description);
        function.put("parameters", parameters);

        Map<String, Object> tool = new LinkedHashMap<>();
        tool.put("type", "function");
        tool.put("function", function);
        return tool;
    }

    private record OllamaChatResponse(OllamaMessage message) {
    }
}

package com.kdt.wellmade.domain.chat;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import com.fasterxml.jackson.databind.JsonNode;
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

/**
 * 챗봇 툴콜링에서 모델이 호출할 수 있는 도구들. 도구 스펙({@link #TOOLS})과 실제 실행({@link #execute})을
 * 함께 갖는다. 모든 도구는 사람이 읽어도 되는 JSON 문자열을 돌려준다(메뉴 경로는 LLM 없이 그대로 씀).
 *
 * 도구 결과에는 계산이 필요한 합계·변화량을 미리 계산해 완성된 문자열로 넣는다 - 모델이 암산하면
 * 표기를 섞거나 부호를 틀리는 게 실측돼서, 더할 일 자체를 없애는 쪽이 프롬프트 금지보다 확실하다.
 */
@Component
public class ChatToolExecutor {

    private static final Logger log = LoggerFactory.getLogger(ChatToolExecutor.class);

    // ChatService.GOAL_LABEL과 같은 값 유지 (버킷 3개, 거의 안 바뀜)
    private static final Map<Goal, String> GOAL_LABEL = Map.of(
            Goal.LOSE, "체중감량",
            Goal.GAIN, "근성장(벌크업)",
            Goal.MAINTAIN, "체형 유지/건강관리"
    );

    /** Ollama에 넘길 도구 스펙 (OpenAI function-calling 호환 형식). Qwen2.5-Instruct가 이 형식을 지원함. */
    static final List<Map<String, Object>> TOOLS = List.of(
            toolDef(
                    "get_meals_for_date",
                    "특정 날짜에 사용자가 기록한 식사 목록(끼니 종류, 메뉴명, 칼로리, 항목별 그램 수)을 가져온다. "
                  + "'어제 뭐 먹었지', '오늘 아침에 뭐 먹었더라', '닭가슴살 몇 그램 먹었지' 같은 질문에는 반드시 "
                  + "이 도구로 실제 기록을 확인하고 답할 것 - 절대 추측하지 말 것.",
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
                    "get_bmi_peer_comparison",
                    "사용자의 최근 BMI가 같은 성별·연령대(국민건강통계) 안에서 어디쯤인지 백분위와 비만도 "
                  + "분류를 가져온다. '내 BMI 또래보다 높아?', '남들이랑 비교하면 어때?'처럼 또래 비교를 "
                  + "물어볼 때 쓸 것 - 절대 추측하지 말 것.",
                    Map.of(),
                    List.of()
            ),
            toolDef(
                    "get_nutrition_peer_comparison",
                    "특정 날짜의 섭취량이 같은 성별·연령대 평균(국민건강통계) 대비 몇 %인지 가져온다. "
                  + "'또래보다 많이 먹었나', '남들 평균이랑 비교해줘' 같은 질문에 쓸 것. 목표 대비 비교는 "
                  + "calculate_nutrient_target이고, 이 도구는 또래 대비 비교라 서로 다르다.",
                    Map.of("date", Map.of(
                            "type", "string",
                            "description", "조회할 날짜, yyyy-MM-dd 형식. 생략하면 오늘."
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
            ),
            toolDef(
                    "recommend_exercises",
                    "사용자가 운동 추천을 원할 때, 부위와 장비 조건에 맞는 운동 후보 목록을 가져온다. "
                  + "'하체 운동 추천해줘', '집에서 할 수 있는 등 운동' 같은 요청에 쓸 것. 부위를 모르면 "
                  + "먼저 사용자에게 물어보고, 부위가 정해지면 이 도구를 호출해 그 결과 안에서만 추천할 것.",
                    Map.of(
                            "body_part", Map.of(
                                    "type", "string",
                                    "description", "운동할 신체 부위. 예: 가슴, 등, 어깨, 팔, 복근, 하체, 종아리, 유산소"
                            ),
                            "equipment", Map.of(
                                    "type", "string",
                                    "description", "사용할 장비나 환경. 예: 맨몸, 덤벨, 바벨, 케이블. 사용자가 말하지 않았으면 생략."
                            )
                    ),
                    List.of("body_part")
            )
    );

    private final UserProfileService userProfileService;
    private final InbodyService inbodyService;
    private final MealLoggingService mealLoggingService;
    private final NutrientTargetCalculator nutrientTargetCalculator;
    private final RestClient aiRestClient;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public ChatToolExecutor(
            UserProfileService userProfileService,
            InbodyService inbodyService,
            MealLoggingService mealLoggingService,
            NutrientTargetCalculator nutrientTargetCalculator,
            RestClient aiRestClient
    ) {
        this.userProfileService = userProfileService;
        this.inbodyService = inbodyService;
        this.mealLoggingService = mealLoggingService;
        this.nutrientTargetCalculator = nutrientTargetCalculator;
        this.aiRestClient = aiRestClient;
    }

    String execute(User user, String name, Map<String, Object> arguments) {
        try {
            return switch (name) {
                case "get_meals_for_date" -> toolGetMealsForDate(user.getId(), arguments);
                case "get_daily_total" -> toolGetDailyTotal(user.getId(), arguments);
                case "get_inbody_history" -> toolGetInbodyHistory(user, arguments);
                case "get_bmi_peer_comparison" -> toolGetBmiPeerComparison(user);
                case "get_nutrition_peer_comparison" -> toolGetNutritionPeerComparison(user, user.getId(), arguments);
                case "calculate_nutrient_target" -> toolCalculateNutrientTarget(user);
                case "recommend_exercises" -> toolRecommendExercises(arguments);
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
                .map(m -> {
                    Map<String, Object> row = new LinkedHashMap<>();
                    row.put("mealType", String.valueOf(m.get("meal_type")));
                    row.put("menuName", String.valueOf(m.get("menu_name")));
                    row.put("kcal", m.get("kcal"));
                    List<Map<String, Object>> foodItems = parseFoodItemsForTool((String) m.get("food_items"));
                    if (!foodItems.isEmpty()) {
                        row.put("items", foodItems);
                    }
                    return row;
                })
                .toList();

        if (simplified.isEmpty()) {
            // 빈 배열만 돌려주면 모델이 그걸 무시하고 식단을 지어낸다. 문장으로 못 박아준다
            return toJson(Map.of("date", date.toString(), "meals", List.of(),
                    "note", date + "에 기록된 식사가 없어요.",
                    "instruction", "없다고만 답하고 식단을 지어내지 마세요."));
        }
        // 합계를 같이 넘긴다 - 없으면 모델이 끼니별 칼로리를 직접 더하다 틀린다(실제로 재현됨).
        // 더할 일 자체를 없애는 게 프롬프트로 금지하는 것보다 확실하다
        long totalKcal = meals.stream()
                .map(m -> m.get("kcal"))
                .filter(Number.class::isInstance)
                .mapToLong(k -> ((Number) k).longValue())
                .sum();
        // 숫자로 주면 모델이 한국어로 읽어내다 표기를 섞어버리는 경우가 있어(실제로 재현됨),
        // 그대로 복사해 쓰면 되는 완성된 문자열로 넘긴다
        return toJson(Map.of("date", date.toString(), "meals", simplified,
                "totalKcal", String.format("%,dkcal", totalKcal)));
    }

    /** food_items 컬럼(JSON 문자열)에서 도구 응답에 필요한 이름/그램 수만 뽑는다. 후보 목록 같은
     *  저장용 부가 필드까지 모델에 넘기면 컨텍스트만 잡아먹으므로 최소한만 남긴다. */
    private List<Map<String, Object>> parseFoodItemsForTool(String foodItemsJson) {
        if (foodItemsJson == null || foodItemsJson.isBlank()) {
            return List.of();
        }
        try {
            List<Map<String, Object>> result = new ArrayList<>();
            for (JsonNode item : objectMapper.readTree(foodItemsJson)) {
                Map<String, Object> m = new LinkedHashMap<>();
                m.put("name", item.path("foodName").asText(""));
                m.put("amountG", item.path("amountG").asDouble(0));
                result.add(m);
            }
            return result;
        } catch (Exception e) {
            log.warn("food_items 파싱 실패, 그램 정보 없이 답함", e);
            return List.of();
        }
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
        if (total.mealCount() == 0) {
            result.put("note", date + "에 기록된 식사가 없어요.");
            result.put("instruction", "없다고만 답하고 수치를 지어내지 마세요.");
        }
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

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("records", records);
        // 개수를 명시하지 않으면 모델이 자기가 넘긴 limit(기본 5)을 결과 개수로 착각한다
        result.put("recordCount", records.size());

        Double first = history.get(history.size() - 1).getWeightKg();
        Double last = history.get(0).getWeightKg();
        if (records.size() == 1) {
            // 1건인데도 "최근 몇 번의 측정 결과는 변함이 없네요"처럼 비교를 지어낸다(실측 8/8).
            // 추세를 말할 수 없다는 걸 문장으로 못 박는다 - 메뉴 경로에서는 이 note가 LLM 없이 그대로 답이 된다.
            result.put("note", last == null
                    ? "인바디 기록이 1건뿐이라 체중 추세는 아직 알 수 없어요."
                    : "인바디 기록이 1건뿐이라 체중 추세는 아직 알 수 없어요. 최근 측정값은 " + last + "kg입니다.");
        } else if (first != null && last != null) {
            // 변화량을 안 주면 모델이 첫 값과 끝 값을 직접 빼서 답한다(실측됨). totalKcal을 미리 계산해
            // 넘기는 것과 같은 이유로, 뺄셈할 일 자체를 없앤다. 부호를 잘못 읽는 것도 막으려고
            // 그대로 복사해 쓰면 되는 완성된 문자열로 넘긴다.
            double change = last - first;
            result.put("weightChange", String.format("%s%.1fkg (%.1fkg -> %.1fkg)",
                    change > 0 ? "+" : "", change, first, last));
        }
        return toJson(result);
    }

    private String toolGetBmiPeerComparison(User user) {
        UserProfile profile = getProfileOrNull(user);
        String peerError = peerProfileError(profile);
        if (peerError != null) {
            return toJson(Map.of("error", peerError));
        }

        InbodyRecord inbody = inbodyService.getLatest(user).orElse(null);
        if (inbody == null || inbody.getBmi() == null) {
            return toJson(Map.of("error", "인바디 기록이 없어서 또래 비교를 할 수 없어요."));
        }

        return callAiServer("/ai/inbody/bmi-insight", Map.of(
                "bmi", inbody.getBmi(),
                "gender", referenceGender(profile.getGender()),
                "birth_year", profile.getBirthYear()
        ), "category", "percentile", "peer_mean", "age_bracket", "message", "source");
    }

    private String toolGetNutritionPeerComparison(User user, Long userId, Map<String, Object> args) {
        UserProfile profile = getProfileOrNull(user);
        String peerError = peerProfileError(profile);
        if (peerError != null) {
            return toJson(Map.of("error", peerError));
        }

        LocalDate date = parseDateArgOrToday(args);
        MealLoggingService.DailyTotal total = mealLoggingService.getTotalForDate(userId, date);
        if (total.mealCount() == 0) {
            return toJson(Map.of("date", date.toString(),
                    "note", date + "에 기록된 식사가 없어서 또래 비교를 할 수 없어요.",
                    "instruction", "없다고만 답하고 수치를 지어내지 마세요."));
        }

        return callAiServer("/ai/nutrition/peer-compare", Map.of(
                "gender", referenceGender(profile.getGender()),
                "birth_year", profile.getBirthYear(),
                "energy_kcal", total.totalCalories(),
                "protein_g", total.totalProteinG(),
                "carbs_g", total.totalCarbsG(),
                "fat_g", total.totalFatG()
        ), "age_bracket", "message", "source");
    }

    /** 또래 비교는 성별×연령대 통계라 둘 중 하나만 없어도 비교 자체가 불가능하다. */
    private String peerProfileError(UserProfile profile) {
        if (profile == null || profile.getGender() == null || profile.getBirthYear() == null) {
            return "성별과 출생연도가 있어야 또래 비교를 할 수 있어요. 마이페이지에서 프로필을 먼저 채워주세요.";
        }
        return null;
    }

    /** 프로필의 MALE/FEMALE을 AI 서버 참조 통계 표기(M/F)로 (frontend/src/lib/aiApi.js와 같은 규칙) */
    private String referenceGender(Gender gender) {
        return gender == Gender.MALE ? "M" : "F";
    }

    /**
     * AI 서버(FastAPI)를 부르고, 응답에서 {@code keep}에 적힌 필드만 남긴다. 응답 전체(끼니별
     * 비교 배열 등)를 그대로 넘기면 같은 내용이 message와 중복돼 컨텍스트만 잡아먹는다.
     *
     * AI 서버는 평소 꺼져 있을 수 있고 여기서 부르는 기능(또래 비교, 운동 추천)은 부가 정보라,
     * 실패해도 대화 전체를 끊지 않고 도구 결과를 error로 돌려준다 - 모델이 "지금은 확인이
     * 안 된다"고 답하게 된다.
     */
    private String callAiServer(String path, Map<String, Object> body, String... keep) {
        JsonNode response;
        try {
            response = aiRestClient.post().uri(path).body(body).retrieve().body(JsonNode.class);
        } catch (RestClientException e) {
            log.info("AI 서버 호출 실패 ({}): {}", path, e.getMessage());
            return toJson(Map.of("error", "AI 서버에서 정보를 가져오지 못했어요. 잠시 후 다시 시도해 주세요."));
        }
        if (response == null) {
            return toJson(Map.of("error", "AI 서버에서 정보를 가져오지 못했어요. 잠시 후 다시 시도해 주세요."));
        }

        Map<String, Object> trimmed = new LinkedHashMap<>();
        for (String field : keep) {
            JsonNode value = response.get(field);
            if (value != null && !value.isNull()) {
                trimmed.put(field, objectMapper.convertValue(value, Object.class));
            }
        }
        return toJson(trimmed);
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

    /**
     * 운동 추천 v1. AI 서버가 exercises_ko.json에서 부위/장비로 거른 후보 목록만 돌려주고,
     * 자연어 추천문은 이 도구 결과를 받은 모델이 (기존 도구 결과 옮기기 경로로) 생성한다.
     * 난이도·기타 조건은 모델이 candidates 중에서 고를 때 참고하게 둔다.
     */
    private String toolRecommendExercises(Map<String, Object> args) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("body_part", argString(args, "body_part", ""));
        String equipment = argString(args, "equipment", null);
        if (equipment != null) {
            body.put("equipment", equipment);
        }
        return callAiServer("/ai/exercise/recommend", body, "body_part", "matched", "candidates", "note");
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
}

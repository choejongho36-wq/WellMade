package com.kdt.wellmade.domain.chat;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.kdt.wellmade.domain.inbody.InbodyRecord;
import com.kdt.wellmade.domain.inbody.InbodyService;
import com.kdt.wellmade.domain.mapage.UserProfile;
import com.kdt.wellmade.domain.mapage.UserProfileService;
import com.kdt.wellmade.domain.nutrition.MealLoggingService;
import com.kdt.wellmade.domain.nutrition.NutrientTarget;
import com.kdt.wellmade.domain.nutrition.NutrientTargetCalculator;
import com.kdt.wellmade.domain.insight.PeerInsightService;
import com.kdt.wellmade.domain.user.User;
import com.kdt.wellmade.domain.workout.WorkoutMemoService;
import com.kdt.wellmade.global.time.AppTime;
import org.springframework.data.domain.PageRequest;

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
                    "사용자가 운동 추천을 원할 때, 부위와 장비 조건에 맞는 운동 목록과 목표별 세트/횟수, "
                  + "주의사항을 가져온다. '하체 운동 추천해줘', '집에서 할 수 있는 등 운동' 같은 요청에 쓸 것. "
                  + "부위를 모르면 먼저 사용자에게 물어보고, 부위가 정해지면 이 도구를 호출해 그 결과 안에서만 "
                  + "추천할 것. 세트 수와 횟수는 직접 정하지 말고 결과의 sets_reps 를 그대로 인용할 것.",
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
            ),
            toolDef(
                    "get_exercise_detail",
                    "운동 하나의 한국어 수행 방법을 가져온다. 추천한 운동 중 사용자가 하나를 지목하거나 "
                  + "('플랭크는 어떻게 해?', '각 운동 설명해줘') 특정 운동의 방법을 물으면 반드시 이 도구를 "
                  + "부를 것. 설명을 직접 지어내지 말 것 - 여러 개를 물으면 운동마다 한 번씩 호출할 것.",
                    Map.of(
                            "name", Map.of(
                                    "type", "string",
                                    "description", "운동 이름. 추천 목록에 보여준 한국어 이름 그대로 넣을 것."
                            )
                    ),
                    List.of("name")
            )
    );

    /**
     * TOOLS에 정의된 도구 이름 모음. 모델이 툴콜을 구조화된 tool_calls 대신 본문 텍스트로 흘렸을 때
     * 그게 툴콜인지 판별하고 회수하는 데 쓴다({@code ChatService.looksLikeToolCallText} 참고) -
     * 도구를 추가하면 여기도 자동으로 따라오도록 TOOLS에서 뽑아 쓴다.
     */
    @SuppressWarnings("unchecked")
    static final Set<String> TOOL_NAMES = TOOLS.stream()
            .map(t -> (String) ((Map<String, Object>) t.get("function")).get("name"))
            .collect(Collectors.toUnmodifiableSet());

    private final UserProfileService userProfileService;
    private final InbodyService inbodyService;
    private final MealLoggingService mealLoggingService;
    private final NutrientTargetCalculator nutrientTargetCalculator;
    private final RestClient aiRestClient;
    private final ObjectMapper objectMapper;
    private final PeerInsightService peerInsightService;
    private final WorkoutMemoService workoutMemoService;
    private final ChatMessageRepository chatMessageRepository;

    public ChatToolExecutor(
            UserProfileService userProfileService,
            InbodyService inbodyService,
            MealLoggingService mealLoggingService,
            NutrientTargetCalculator nutrientTargetCalculator,
            RestClient aiRestClient,
            ObjectMapper objectMapper,
            PeerInsightService peerInsightService,
            WorkoutMemoService workoutMemoService,
            ChatMessageRepository chatMessageRepository
    ) {
        this.userProfileService = userProfileService;
        this.inbodyService = inbodyService;
        this.mealLoggingService = mealLoggingService;
        this.nutrientTargetCalculator = nutrientTargetCalculator;
        this.aiRestClient = aiRestClient;
        this.objectMapper = objectMapper;
        this.peerInsightService = peerInsightService;
        this.workoutMemoService = workoutMemoService;
        this.chatMessageRepository = chatMessageRepository;
    }

    /**
     * 도구 실행 결과.
     *
     * json은 모델에게 줄 내용이고, links는 모델을 거치지 않고 화면에 그대로 그릴 버튼이다
     * (운동 추천의 국민체력100 영상). URL을 모델에게 주면 답변 안에 주소를 그대로 뱉거나
     * 없는 주소를 지어내므로, 링크는 모델을 통과시키지 않는다.
     */
    record ToolResult(String json, List<Map<String, String>> links) {
        static ToolResult of(String json) {
            return new ToolResult(json, List.of());
        }
    }

    ToolResult execute(User user, String name, Map<String, Object> arguments) {
        try {
            return switch (name) {
                case "get_meals_for_date" -> ToolResult.of(toolGetMealsForDate(user.getId(), arguments));
                case "get_daily_total" -> ToolResult.of(toolGetDailyTotal(user.getId(), arguments));
                case "get_inbody_history" -> ToolResult.of(toolGetInbodyHistory(user, arguments));
                case "get_bmi_peer_comparison" -> ToolResult.of(toolGetBmiPeerComparison(user));
                case "get_nutrition_peer_comparison" ->
                        ToolResult.of(toolGetNutritionPeerComparison(user, user.getId(), arguments));
                case "calculate_nutrient_target" -> ToolResult.of(toolCalculateNutrientTarget(user));
                case "recommend_exercises" -> toolRecommendExercises(user, arguments);
                case "get_exercise_detail" -> ToolResult.of(toolGetExerciseDetail(arguments));
                default -> ToolResult.of(toJson(Map.of("error", "알 수 없는 도구입니다: " + name)));
            };
        } catch (Exception e) {
            log.error("도구 실행 실패: {}", name, e);
            return ToolResult.of(toJson(Map.of("error", "도구 실행 중 문제가 발생했어요.")));
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

    // 또래 비교의 실제 내용(프로필 검증, BMI 유효성·교차검증, 오늘 비교 주의문구, AI 서버 호출)은
    // PeerInsightService에 있다 - 마이페이지/영양소 화면도 같은 서비스를 쓴다. 여기서는 모델이
    // 읽을 필드만 남기는 일만 한다.
    private String toolGetBmiPeerComparison(User user) {
        return trim(peerInsightService.bmiInsight(user),
                "error", "category", "percentile", "peer_mean", "age_bracket", "warning", "message", "source");
    }

    private String toolGetNutritionPeerComparison(User user, Long userId, Map<String, Object> args) {
        return trim(peerInsightService.nutritionPeerCompare(user, user.getId(), parseDateArgOrToday(args)),
                "error", "date", "note", "instruction", "age_bracket", "message", "source");
    }

    /**
     * 도구 결과에서 {@code keep}에 적힌 필드만 남긴다. 응답 전체(끼니별 비교 배열 등)를 그대로
     * 넘기면 같은 내용이 message와 중복돼 컨텍스트만 잡아먹는다.
     */
    private String trim(JsonNode response, String... keep) {
        Map<String, Object> trimmed = new LinkedHashMap<>();
        for (String field : keep) {
            JsonNode value = response.get(field);
            if (value != null && !value.isNull()) {
                trimmed.put(field, objectMapper.convertValue(value, Object.class));
            }
        }
        return toJson(trimmed);
    }

    /**
     * AI 서버(FastAPI)를 부르고, 응답에서 {@code keep}에 적힌 필드만 남긴다.
     *
     * AI 서버는 평소 꺼져 있을 수 있고 여기서 부르는 기능(운동 추천)은 부가 정보라,
     * 실패해도 대화 전체를 끊지 않고 도구 결과를 error로 돌려준다 - 모델이 "지금은 확인이
     * 안 된다"고 답하게 된다.
     */
    private String callAiServer(String path, Map<String, Object> body, String... keep) {
        JsonNode response = callAiServerRaw(path, body);
        if (response == null) {
            return toJson(Map.of("error", AI_UNAVAILABLE));
        }
        return trim(response, keep);
    }

    /** 응답을 손대지 않고 그대로 돌려준다. 실패하면 null (호출부가 안내 문구를 만든다) */
    private JsonNode callAiServerRaw(String path, Map<String, Object> body) {
        try {
            return aiRestClient.post().uri(path).body(body).retrieve().body(JsonNode.class);
        } catch (RestClientException e) {
            log.info("AI 서버 호출 실패 ({}): {}", path, e.getMessage());
            return null;
        }
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
        result.put("goal", profile.getGoal().label());
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
    /** 최근 운동 메모를 읽을 기간. AI 서버의 RECENT_DAYS와 맞춰야 함 */
    private static final String AI_UNAVAILABLE = "AI 서버에서 정보를 가져오지 못했어요. 잠시 후 다시 시도해 주세요.";

    private static final int WORKOUT_MEMO_DAYS = 7;
    /** 같은 추천이 반복되지 않게 훑어볼 최근 챗봇 답변 수 */
    private static final int RECENT_REPLY_LIMIT = 10;
    /** 답변 한 건에서 넘길 길이. 운동 이름은 앞부분에 나오므로 이만큼이면 다 잡힌다 */
    private static final int RECENT_REPLY_MAX_CHARS = 500;
    /** 답변 아래에 붙일 영상 버튼 수 상한 - 넘치면 말풍선이 링크 목록이 된다 */
    private static final int MAX_VIDEO_LINKS = 3;

    /**
     * 운동 추천. 부위·장비만 넘기던 것에서 목표·나이·최근 운동 기록까지 같이 넘기도록 바뀌었다.
     *
     * 무엇을 몇 세트 할지는 AI 서버가 규칙으로 정하고(app/exercise/recommend.py), 모델은 그
     * 결과를 문장으로 옮기기만 한다 - 메뉴 경로에서 이미 검증한 분담이다. 세트/횟수를 모델이
     * 지어내게 두면 같은 목표에도 답이 흔들리고 근거를 댈 수 없다.
     */
    private ToolResult toolRecommendExercises(User user, Map<String, Object> args) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("body_part", argString(args, "body_part", ""));
        String equipment = argString(args, "equipment", null);
        if (equipment != null) {
            body.put("equipment", equipment);
        }

        UserProfile profile = getProfileOrNull(user);
        if (profile != null) {
            if (profile.getGoal() != null) {
                body.put("goal", profile.getGoal().name());
            }
            if (profile.getBirthYear() != null) {
                // 연 나이(만 나이보다 최대 1살 많음). 여기서는 "50대 이상이면 고급 동작 제외"
                // 정도로만 쓰이므로 그 오차가 결과를 바꾸지 않는다.
                body.put("age", AppTime.today().getYear() - profile.getBirthYear());
            }
        }
        body.put("recent_workouts", recentWorkouts(user));
        // 최근 답변 원문을 넘기면 AI 서버가 그 안에 등장한 운동 이름을 빼준다. 운동 이름 목록은
        // 그쪽 큐레이션 파일에만 있으므로, 양쪽에 이름을 복제하지 않으려는 분담이다.
        body.put("exclude_from_text", recentAssistantReplies(user));

        JsonNode response = callAiServerRaw("/ai/exercise/recommend", body);
        if (response == null) {
            return ToolResult.of(toJson(Map.of("error", AI_UNAVAILABLE)));
        }
        // 모델에게는 URL을 주지 않는다 - 영상은 아래 links로 화면에 직접 그린다.
        return new ToolResult(trimRecommendation(response), videoLinks(response));
    }

    /** 최근 며칠간의 운동 메모 원문. 부위 키워드를 읽는 건 AI 서버 몫(사전이 거기 있음) */
    private List<Map<String, String>> recentWorkouts(User user) {
        LocalDate today = AppTime.today();
        return workoutMemoService.getBetween(user, today.minusDays(WORKOUT_MEMO_DAYS), today);
    }

    private List<String> recentAssistantReplies(User user) {
        return chatMessageRepository
                .findByUserOrderByCreatedAtDesc(user, PageRequest.of(0, RECENT_REPLY_LIMIT)).stream()
                .filter(m -> "assistant".equals(m.getRole()))
                .map(m -> m.getContent().length() <= RECENT_REPLY_MAX_CHARS
                        ? m.getContent()
                        : m.getContent().substring(0, RECENT_REPLY_MAX_CHARS))
                .toList();
    }

    /**
     * 모델에게 줄 추천 결과. 후보에서 영상(URL)과 화면용 필드를 빼고, 문장을 만드는 데 필요한
     * 것만 남긴다 - 응답을 통째로 넘기면 컨텍스트만 잡아먹고 URL이 답변에 새어나온다.
     */
    private String trimRecommendation(JsonNode response) {
        Map<String, Object> result = new LinkedHashMap<>();
        for (String field : new String[] {"body_part_ko", "goal", "plan", "workout_note", "cautions", "note"}) {
            JsonNode value = response.get(field);
            if (value != null && !value.isNull()) {
                result.put(field, objectMapper.convertValue(value, Object.class));
            }
        }

        List<Map<String, Object>> candidates = new ArrayList<>();
        for (JsonNode candidate : response.path("candidates")) {
            Map<String, Object> row = new LinkedHashMap<>();
            for (String field : new String[] {"name", "difficulty", "equipment", "sets_reps", "instructions_ko"}) {
                row.put(field, candidate.path(field).asText(""));
            }
            candidates.add(row);
        }
        result.put("candidates", candidates);
        return toJson(result);
    }

    /**
     * 후보에 붙어 온 국민체력100 영상을 말풍선 아래 버튼으로 그릴 형태로 바꾼다.
     *
     * 같은 영상이 여러 운동에 붙을 수 있어서(잭 점프/스타 점프 -> 같은 점핑잭 영상) URL로
     * 중복을 없앤다. 난이도 태그는 운동 난이도와 같을 때만 보여준다 - 영상 데이터에 초급이
     * 적어서 "초급 운동 ▶ (중급) 영상"이 자주 나오는데, 그 조합은 사용자에게 혼란만 준다.
     */
    List<Map<String, String>> videoLinks(JsonNode response) {
        List<Map<String, String>> links = new ArrayList<>();
        Set<String> seenUrls = new HashSet<>();
        for (JsonNode candidate : response.path("candidates")) {
            JsonNode video = candidate.path("related_video");
            String url = video.path("video_url").asText("");
            if (url.isBlank() || links.size() >= MAX_VIDEO_LINKS || !seenUrls.add(url)) {
                continue;
            }

            List<String> tags = new ArrayList<>();
            String level = video.path("level").asText("");
            if (!level.isBlank() && level.equals(candidate.path("difficulty").asText(""))) {
                tags.add(level);
            }
            for (String field : new String[] {"place", "tool"}) {
                String tag = video.path(field).asText("");
                if (!tag.isBlank()) {
                    tags.add(tag);
                }
            }
            String name = video.path("name").asText("운동 영상");
            String label = tags.isEmpty() ? name : name + " (" + String.join(" · ", tags) + ")";
            links.add(Map.of("label", label, "url", url));
        }
        return links;
    }

    /**
     * 지목한 운동 1건의 한국어 수행 방법. 이 도구가 없던 시절엔 모델이 설명을 직접 지어냈고,
     * 근거 없는 자유 생성이라 중국어로 새는 턴이 나왔다(실측) - 데이터에 있는 한국어 설명을
     * 넘겨서 "창작"을 "옮겨쓰기"로 바꾼다.
     */
    private String toolGetExerciseDetail(Map<String, Object> args) {
        String name = argString(args, "name", "");
        return callAiServer("/ai/exercise/detail", Map.of("name", name),
                "found", "name", "target", "equipment", "instructions_ko", "note");
    }

    private LocalDate parseDateArgOrToday(Map<String, Object> args) {
        String raw = argString(args, "date", null);
        if (raw == null) {
            return AppTime.today();
        }
        try {
            return LocalDate.parse(raw);
        } catch (Exception e) {
            // 모델이 날짜 형식을 잘못 넣으면(예: "어제"를 계산 안 하고 그대로 보냄) 오늘로 대체.
            // 여기서 예외를 던지면 도구 호출 자체가 실패해서 답변을 아예 못 받는 게 더 나쁨.
            log.warn("도구 호출의 date 인자를 파싱하지 못해 오늘 날짜로 대체함: {}", raw);
            return AppTime.today();
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

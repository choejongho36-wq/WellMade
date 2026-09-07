package com.kdt.wellmade.domain.insight;

import java.time.LocalDate;
import java.util.LinkedHashMap;
import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.kdt.wellmade.domain.inbody.InbodyRecord;
import com.kdt.wellmade.domain.inbody.InbodyService;
import com.kdt.wellmade.domain.mapage.Gender;
import com.kdt.wellmade.domain.mapage.UserProfile;
import com.kdt.wellmade.domain.mapage.UserProfileService;
import com.kdt.wellmade.domain.nutrition.MealLoggingService;
import com.kdt.wellmade.domain.user.User;
import com.kdt.wellmade.global.time.AppTime;

/**
 * 또래 비교(BMI / 영양 섭취) 한 곳.
 *
 * 예전엔 챗봇 도구(ChatToolExecutor)와 화면(프론트의 aiApi.js)이 각자 AI 서버를 불렀다.
 * 그래서 (1) 브라우저가 AI 서버를 인증 없이 직접 두드릴 수 있었고 (2) 검증·주의문구를
 * 넣으려면 두 군데를 똑같이 고쳐야 했다. 이제 두 경로 모두 이 서비스를 지난다 -
 * AI 서버를 부르는 건 백엔드뿐이고, 프론트는 JWT가 붙는 /api/... 만 부른다.
 *
 * 값 자체(BMI, 섭취량)는 클라이언트가 아니라 서버가 DB에서 읽는다. 넘겨받으면 "내 BMI는
 * 18입니다" 같은 임의 값으로도 비교가 되고, 그건 사용자 데이터에 대한 답이 아니게 된다.
 */
@Service
public class PeerInsightService {

    private static final Logger log = LoggerFactory.getLogger(PeerInsightService.class);

    /**
     * 사람이 가질 수 있는 BMI 범위. 인바디 OCR이 소수점을 놓치거나(2.5) 자릿수를 잘못 읽으면(250)
     * 그대로 "저체중"/"3단계 비만"으로 확정돼 버린다. AI 서버 스키마에도 같은 제약이 있지만,
     * 거기서 걸리면 422라 사용자에게 이유를 설명할 수 없어서 여기서 먼저 막는다.
     */
    private static final double MIN_PLAUSIBLE_BMI = 10.0;
    private static final double MAX_PLAUSIBLE_BMI = 60.0;

    private static final String AI_UNAVAILABLE =
            "또래 비교 정보를 가져오지 못했어요. 잠시 후 다시 시도해 주세요.";

    private final UserProfileService userProfileService;
    private final InbodyService inbodyService;
    private final MealLoggingService mealLoggingService;
    private final RestClient aiRestClient;
    private final ObjectMapper objectMapper;

    public PeerInsightService(
            UserProfileService userProfileService,
            InbodyService inbodyService,
            MealLoggingService mealLoggingService,
            RestClient aiRestClient,
            ObjectMapper objectMapper
    ) {
        this.userProfileService = userProfileService;
        this.inbodyService = inbodyService;
        this.mealLoggingService = mealLoggingService;
        this.aiRestClient = aiRestClient;
        this.objectMapper = objectMapper;
    }

    /**
     * 가장 최근 인바디 기록의 BMI에 대한 또래 위치 + 비만도 분류.
     * 과거 기록과의 추이는 다루지 않는다 - 이 조회의 답은 "지금 내가 어디쯤인가" 하나다
     * (체중 추세는 인바디 이력 조회 쪽 몫이다).
     *
     * 실패하거나 비교할 수 없으면 {@code error} 필드만 담긴 객체를 돌려준다 - 또래 비교는
     * 부가 정보라, 못 가져왔다고 해서 인바디 화면이나 대화가 막히면 안 된다.
     */
    public ObjectNode bmiInsight(User user) {
        UserProfile profile = getProfileOrNull(user);
        String profileError = peerProfileError(profile);
        if (profileError != null) {
            return error(profileError);
        }

        InbodyRecord latest = inbodyService.getLatest(user).orElse(null);
        if (latest == null || latest.getBmi() == null) {
            return error("인바디 기록이 없어서 또래 비교를 할 수 없어요.");
        }

        double bmi = latest.getBmi();
        if (bmi < MIN_PLAUSIBLE_BMI || bmi > MAX_PLAUSIBLE_BMI) {
            return error(String.format(
                    "인바디에 기록된 체질량지수(%.1f)가 정상 범위를 벗어나서 또래 비교를 할 수 없어요."
                            + " 인바디를 다시 등록해 주세요.", bmi));
        }

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("bmi", bmi);
        body.put("gender", referenceGender(profile.getGender()));
        body.put("birth_year", profile.getBirthYear());
        // 키(프로필)와 체중(인바디)을 같이 넘겨 BMI를 교차검증하게 한다.
        // 크게 어긋나면 AI 서버가 warning을 붙여 돌려준다 - 값을 고치지는 않는다.
        body.put("height_cm", profile.getHeightCm());
        body.put("weight_kg", latest.getWeightKg());

        return callAiServer("/ai/inbody/bmi-insight", body);
    }

    /**
     * 하루 섭취량을 같은 성별·연령대 평균과 비교한다.
     *
     * 원 통계는 "하루 전체" 섭취량이라 비교 대상도 끝난 하루여야 한다. 오전 10시에 아침만
     * 기록한 상태로 비교하면 "또래 평균의 28%"가 나오는데, 그건 적게 먹었다는 뜻이 아니다.
     * 그래서 오늘 날짜면 결과에 note를 실어 "아직 진행 중"이라고 알린다 - 날짜와 시각을
     * 아는 건 AI 서버가 아니라 여기다.
     */
    public ObjectNode nutritionPeerCompare(User user, Long userId, LocalDate date) {
        UserProfile profile = getProfileOrNull(user);
        String profileError = peerProfileError(profile);
        if (profileError != null) {
            return error(profileError);
        }

        MealLoggingService.DailyTotal total = mealLoggingService.getTotalForDate(userId, date);
        if (total.mealCount() == 0) {
            ObjectNode empty = objectMapper.createObjectNode();
            empty.put("date", date.toString());
            empty.put("note", date + "에 기록된 식사가 없어서 또래 비교를 할 수 없어요.");
            empty.put("instruction", "없다고만 답하고 수치를 지어내지 마세요.");
            return empty;
        }

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("gender", referenceGender(profile.getGender()));
        body.put("birth_year", profile.getBirthYear());
        body.put("energy_kcal", total.totalCalories());
        body.put("protein_g", total.totalProteinG());
        body.put("carbs_g", total.totalCarbsG());
        body.put("fat_g", total.totalFatG());

        ObjectNode result = callAiServer("/ai/nutrition/peer-compare", body);
        result.put("date", date.toString());

        String partialDayNote = partialDayNote(date, total.mealCount());
        if (partialDayNote != null && !result.has("error")) {
            result.put("note", partialDayNote);
            result.put("instruction", "비교 수치를 말할 때 아직 하루가 끝나지 않았다는 점을 반드시 같이 알리세요.");
        }
        return result;
    }

    /** 아직 끝나지 않은 오늘을 비교했을 때 붙일 주의 문구. 지난 날짜면 null. */
    String partialDayNote(LocalDate date, int mealCount) {
        if (!date.equals(AppTime.today())) {
            return null;
        }
        return String.format(
                "오늘은 아직 하루가 끝나지 않았어요(현재 %d시, 기록된 끼니 %d건)."
                        + " 또래 평균은 하루 전체 섭취량이라, 지금 비교는 참고만 해주세요.",
                AppTime.nowTime().getHour(), mealCount);
    }

    /** 또래 비교는 성별×연령대 통계라 둘 중 하나만 없어도 비교 자체가 불가능하다. */
    private String peerProfileError(UserProfile profile) {
        if (profile == null || profile.getGender() == null || profile.getBirthYear() == null) {
            return "성별과 출생연도가 있어야 또래 비교를 할 수 있어요. 마이페이지에서 프로필을 먼저 채워주세요.";
        }
        return null;
    }

    /** 프로필의 MALE/FEMALE을 AI 서버 참조 통계 표기(M/F)로 */
    private String referenceGender(Gender gender) {
        return gender == Gender.MALE ? "M" : "F";
    }

    private ObjectNode callAiServer(String path, Map<String, Object> body) {
        JsonNode response;
        try {
            response = aiRestClient.post().uri(path).body(body).retrieve().body(JsonNode.class);
        } catch (RestClientException e) {
            // AI 서버는 평소 꺼져 있을 수 있다. 부가 정보라 실패해도 화면/대화를 끊지 않는다.
            log.info("AI 서버 호출 실패 ({}): {}", path, e.getMessage());
            return error(AI_UNAVAILABLE);
        }
        if (response == null || !response.isObject()) {
            return error(AI_UNAVAILABLE);
        }
        return (ObjectNode) response;
    }

    private ObjectNode error(String message) {
        ObjectNode node = objectMapper.createObjectNode();
        node.put("error", message);
        return node;
    }

    private UserProfile getProfileOrNull(User user) {
        try {
            return userProfileService.getProfile(user);
        } catch (IllegalArgumentException e) {
            return null;
        }
    }
}

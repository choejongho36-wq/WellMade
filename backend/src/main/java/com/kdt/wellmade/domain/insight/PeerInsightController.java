package com.kdt.wellmade.domain.insight;

import java.time.LocalDate;
import java.util.Map;

import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.kdt.wellmade.domain.user.User;
import com.kdt.wellmade.domain.user.UserService;
import com.kdt.wellmade.global.time.AppTime;

/**
 * 또래 비교 API.
 *
 * 예전엔 화면이 AI 서버(/ai/...)를 브라우저에서 직접 불렀다. 상태 없는 통계 조회라 유출될
 * 정보는 없었지만 인증이 전혀 없어서 아무나 무제한으로 때릴 수 있었고, 챗봇 도구는 이미
 * 백엔드를 거치고 있어서 같은 기능에 경로가 두 개였다. 이제 둘 다 여기(JWT 검증 뒤)를 지난다.
 *
 * 비교할 값(BMI, 하루 섭취량)은 요청 본문이 아니라 서버가 DB에서 읽는다 - 그래야 "내 기록"에
 * 대한 답이 된다. 그래서 파라미터가 날짜뿐이고 GET이다.
 */
@RestController
@RequestMapping("/api/users/me/insights")
public class PeerInsightController {

    private final PeerInsightService peerInsightService;
    private final UserService userService;
    private final ObjectMapper objectMapper;

    public PeerInsightController(
            PeerInsightService peerInsightService, UserService userService, ObjectMapper objectMapper) {
        this.peerInsightService = peerInsightService;
        this.userService = userService;
        this.objectMapper = objectMapper;
    }

    /** 최신 인바디 BMI의 또래 위치 + 비만도 분류 + 백분위 추이 */
    @GetMapping("/bmi")
    public Map<String, Object> bmi(@AuthenticationPrincipal Long userId) {
        return toResponse(peerInsightService.bmiInsight(userService.getUser(userId)));
    }

    /** 그 날 섭취량을 같은 성별·연령대 평균과 비교 (date 생략 시 오늘) */
    @GetMapping("/nutrition")
    public Map<String, Object> nutrition(
            @AuthenticationPrincipal Long userId,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate date
    ) {
        User user = userService.getUser(userId);
        return toResponse(
                peerInsightService.nutritionPeerCompare(user, userId, date != null ? date : AppTime.today()));
    }

    /**
     * 서비스가 만든 트리(Jackson 2)를 Map으로 풀어서 돌려준다.
     *
     * JsonNode를 그대로 반환하면 안 된다 - Spring Boot 4.1의 응답 컨버터는 Jackson 3
     * (tools.jackson)인데 이 JsonNode는 Jackson 2(com.fasterxml.jackson)라, 트리로 알아보지
     * 못하고 평범한 객체로 취급해 {@code {"array":false,"bigDecimal":false,...}} 같은 내부
     * 판별자만 내보낸다. 예외가 안 나고 조용히 엉뚱한 JSON이 나가서 더 위험하다(실측).
     * Map/List로 바꿔 두면 어느 쪽 Jackson이 직렬화해도 같은 결과가 된다.
     */
    private Map<String, Object> toResponse(JsonNode node) {
        return objectMapper.convertValue(node, new TypeReference<Map<String, Object>>() {});
    }
}

package com.kdt.wellmade.domain.insight;

import java.time.LocalDate;

import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.fasterxml.jackson.databind.JsonNode;
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

    public PeerInsightController(PeerInsightService peerInsightService, UserService userService) {
        this.peerInsightService = peerInsightService;
        this.userService = userService;
    }

    /** 최신 인바디 BMI의 또래 위치 + 비만도 분류 + 백분위 추이 */
    @GetMapping("/bmi")
    public JsonNode bmi(@AuthenticationPrincipal Long userId) {
        return peerInsightService.bmiInsight(userService.getUser(userId));
    }

    /** 그 날 섭취량을 같은 성별·연령대 평균과 비교 (date 생략 시 오늘) */
    @GetMapping("/nutrition")
    public JsonNode nutrition(
            @AuthenticationPrincipal Long userId,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate date
    ) {
        User user = userService.getUser(userId);
        return peerInsightService.nutritionPeerCompare(user, userId, date != null ? date : AppTime.today());
    }
}

package com.kdt.wellmade.domain.workout;

import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.kdt.wellmade.domain.report.ReportSourceType;
import com.kdt.wellmade.domain.user.UserService;

/**
 * 실시간 세션/사진측정 코칭이 끝날 때 프론트가 결과 요약을 남기는 API. 관리자 대시보드
 * 집계 전용이라 실패해도 사용자 화면(리포트 표시 등)에는 영향이 없어야 한다 — 프론트도
 * 이 호출을 fire-and-forget으로 감싸서 쓴다(useSquatCoachingSession.js/usePhotoCoachingSession.js).
 */
@RestController
@RequestMapping("/api/workout/sessions")
public class WorkoutSessionController {

    private final WorkoutSessionLogRepository workoutSessionLogRepository;
    private final UserService userService;
    private final ObjectMapper objectMapper;

    public WorkoutSessionController(
            WorkoutSessionLogRepository workoutSessionLogRepository, UserService userService, ObjectMapper objectMapper) {
        this.workoutSessionLogRepository = workoutSessionLogRepository;
        this.userService = userService;
        this.objectMapper = objectMapper;
    }

    record SessionLogRequest(
            ReportSourceType sourceType,
            boolean resultNormal,
            Integer totalReps,
            Integer abnormalReps,
            Map<String, Integer> issueCounts
    ) {}

    @PostMapping
    public ResponseEntity<Void> log(@AuthenticationPrincipal Long userId, @RequestBody SessionLogRequest request) {
        if (request.sourceType() == null) {
            return ResponseEntity.badRequest().build();
        }

        String issueCountsJson = null;
        if (request.issueCounts() != null && !request.issueCounts().isEmpty()) {
            try {
                issueCountsJson = objectMapper.writeValueAsString(request.issueCounts());
            } catch (Exception e) {
                issueCountsJson = null; // 집계용 부가 정보라, 직렬화가 실패해도 로그 자체는 남긴다
            }
        }

        workoutSessionLogRepository.save(WorkoutSessionLog.builder()
                .user(userService.getUser(userId))
                .sourceType(request.sourceType())
                .resultNormal(request.resultNormal())
                .totalReps(request.totalReps())
                .abnormalReps(request.abnormalReps())
                .issueCounts(issueCountsJson)
                .build());

        return ResponseEntity.ok().build();
    }
}

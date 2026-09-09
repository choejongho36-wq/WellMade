package com.kdt.wellmade.global.admin;

import java.time.LocalDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.kdt.wellmade.domain.chat.ChatMessageRepository;
import com.kdt.wellmade.domain.inbody.InbodyRecordRepository;
import com.kdt.wellmade.domain.nutrition.MealLoggingService;
import com.kdt.wellmade.domain.report.PoseReportRepository;
import com.kdt.wellmade.domain.report.ReportStatus;
import com.kdt.wellmade.domain.user.UserRepository;
import com.kdt.wellmade.domain.workout.WorkoutSessionLog;
import com.kdt.wellmade.domain.workout.WorkoutSessionLogRepository;
import com.kdt.wellmade.global.monitoring.LlmCallLog;
import com.kdt.wellmade.global.monitoring.LlmCallLogRepository;
import com.kdt.wellmade.global.time.AppTime;

import lombok.RequiredArgsConstructor;

/**
 * 대시보드 홈 통계. 예전 Thymeleaf AdminController.dashboard()에서 시작했지만(2026-09-09
 * 프론트 REST 전환), 회원/신고 2개 카드뿐이던 것을 서비스 전체 도메인(운동/식단/인바디/챗봇/
 * AI 모니터링)으로 넓혔다 — 근거: claude/wellmade-ai-progress.md 및 대화에서 정리된 대시보드
 * 구성안.
 *
 * "오늘"은 전부 AppTime(KST) 기준 자정부터, "이번 주"는 오늘 포함 최근 7일이다.
 */
@RestController
@RequestMapping("/api/admin/dashboard")
@RequiredArgsConstructor
public class AdminDashboardController {

    private final UserRepository userRepository;
    private final PoseReportRepository poseReportRepository;
    private final WorkoutSessionLogRepository workoutSessionLogRepository;
    private final MealLoggingService mealLoggingService;
    private final InbodyRecordRepository inbodyRecordRepository;
    private final ChatMessageRepository chatMessageRepository;
    private final LlmCallLogRepository llmCallLogRepository;
    private final ObjectMapper objectMapper;

    record SummaryCard(long totalUsers, long todaySignups, long dau, long todaySessions) {}

    record WorkoutStats(
            long todaySessions, long weekSessions,
            long todayNormal, long todayAbnormal,
            Map<String, Long> todayIssueCounts) {}

    record NutritionStats(long todayMealLogs, long todayLoggingUsers) {}

    record RecentInbody(Long id, String userEmail, Double weightKg, LocalDateTime createdAt) {}

    record InbodyStats(long weekNewRecords, List<RecentInbody> recent) {}

    record ToolUsage(String toolName, long count) {}

    record ChatStats(long todayConversations, long todayActiveUsers, double avgMessagesPerUser, List<ToolUsage> topTools) {}

    record MonitoringStats(
            long todayLlmCalls, long todayLlmFallbacks, Double avgLatencyMs,
            long todayToolCalls, long todayToolFailures) {}

    record RecentUser(Long id, String email, LocalDateTime createdAt) {}

    record RecentSession(Long id, String userEmail, String sourceType, boolean resultNormal, LocalDateTime createdAt) {}

    record RecentActivity(List<RecentUser> recentUsers, List<RecentSession> recentSessions) {}

    record ReportStats(long pending, long approved, long rejected) {}

    record DashboardResponse(
            SummaryCard summary,
            ReportStats reports,
            WorkoutStats workout,
            NutritionStats nutrition,
            InbodyStats inbody,
            ChatStats chat,
            MonitoringStats monitoring,
            RecentActivity recent) {}

    @GetMapping
    public DashboardResponse dashboard() {
        LocalDateTime todayStart = AppTime.today().atStartOfDay();
        LocalDateTime weekStart = AppTime.today().minusDays(6).atStartOfDay();

        long todaySessions = workoutSessionLogRepository.countByCreatedAtAfter(todayStart);

        SummaryCard summary = new SummaryCard(
                userRepository.count(),
                userRepository.countByCreatedAtAfter(todayStart),
                userRepository.countByLastActiveAtAfter(todayStart),
                todaySessions);

        ReportStats reports = new ReportStats(
                poseReportRepository.countByStatus(ReportStatus.PENDING),
                poseReportRepository.countByStatus(ReportStatus.APPROVED),
                poseReportRepository.countByStatus(ReportStatus.REJECTED));

        List<WorkoutSessionLog> todaySessionLogs = workoutSessionLogRepository.findByCreatedAtAfterOrderByCreatedAtDesc(todayStart);
        WorkoutStats workout = new WorkoutStats(
                todaySessions,
                workoutSessionLogRepository.countByCreatedAtAfter(weekStart),
                workoutSessionLogRepository.countByResultNormalAndCreatedAtAfter(true, todayStart),
                workoutSessionLogRepository.countByResultNormalAndCreatedAtAfter(false, todayStart),
                aggregateIssueCounts(todaySessionLogs));

        MealLoggingService.AdminTodayStats mealStats = mealLoggingService.getAdminTodayStats();
        NutritionStats nutrition = new NutritionStats(mealStats.mealCount(), mealStats.userCount());

        List<RecentInbody> recentInbody = inbodyRecordRepository.findTop5ByOrderByCreatedAtDesc().stream()
                .map(r -> new RecentInbody(r.getId(), r.getUser().getEmail(), r.getWeightKg(), r.getCreatedAt()))
                .toList();
        InbodyStats inbody = new InbodyStats(inbodyRecordRepository.countByCreatedAtAfter(weekStart), recentInbody);

        long chatConversations = chatMessageRepository.countByRoleAndCreatedAtAfter("user", todayStart);
        long chatActiveUsers = chatMessageRepository.countDistinctUsersByRoleAndCreatedAtAfter("user", todayStart);
        double avgMessagesPerUser = chatActiveUsers > 0 ? (double) chatConversations / chatActiveUsers : 0;
        List<ToolUsage> topTools = aggregateToolUsage(
                llmCallLogRepository.findByFeatureAndCreatedAtAfter(LlmCallLog.Feature.CHAT_TOOL_CALL, todayStart));
        ChatStats chat = new ChatStats(chatConversations, chatActiveUsers, avgMessagesPerUser, topTools);

        MonitoringStats monitoring = new MonitoringStats(
                llmCallLogRepository.countByFeatureAndCreatedAtAfter(LlmCallLog.Feature.CHAT_REPLY, todayStart),
                llmCallLogRepository.countByFeatureAndSuccessFalseAndCreatedAtAfter(LlmCallLog.Feature.CHAT_REPLY, todayStart),
                llmCallLogRepository.averageLatencyMs(LlmCallLog.Feature.CHAT_REPLY, todayStart),
                llmCallLogRepository.countByFeatureAndCreatedAtAfter(LlmCallLog.Feature.CHAT_TOOL_CALL, todayStart),
                llmCallLogRepository.countByFeatureAndSuccessFalseAndCreatedAtAfter(LlmCallLog.Feature.CHAT_TOOL_CALL, todayStart));

        List<RecentUser> recentUsers = userRepository.findTop5ByOrderByCreatedAtDesc().stream()
                .map(u -> new RecentUser(u.getId(), u.getEmail(), u.getCreatedAt()))
                .toList();
        List<RecentSession> recentSessions = workoutSessionLogRepository.findTop5ByOrderByCreatedAtDesc().stream()
                .map(s -> new RecentSession(s.getId(), s.getUser().getEmail(), s.getSourceType().name(), s.isResultNormal(), s.getCreatedAt()))
                .toList();
        RecentActivity recent = new RecentActivity(recentUsers, recentSessions);

        return new DashboardResponse(summary, reports, workout, nutrition, inbody, chat, monitoring, recent);
    }

    // WorkoutSessionLog.issueCounts(JSON 문자열)를 부위별로 합산한다. 부위 종류가 적어(무릎모임/
    // 발뒤꿈치 등 한 자릿수) 자바에서 더하는 쪽이 DB JSON 함수를 쓰는 것보다 단순하다.
    private Map<String, Long> aggregateIssueCounts(List<WorkoutSessionLog> logs) {
        Map<String, Long> result = new LinkedHashMap<>();
        for (WorkoutSessionLog session : logs) {
            if (session.getIssueCounts() == null) {
                continue;
            }
            try {
                JsonNode node = objectMapper.readTree(session.getIssueCounts());
                node.fields().forEachRemaining(entry -> result.merge(entry.getKey(), entry.getValue().asLong(), Long::sum));
            } catch (Exception e) {
                // 저장 시점에 이미 검증된 JSON이라 정상 상황에선 안 탄다 - 방어적으로만 건너뜀
            }
        }
        return result;
    }

    private List<ToolUsage> aggregateToolUsage(List<LlmCallLog> logs) {
        Map<String, Long> counts = new LinkedHashMap<>();
        for (LlmCallLog log : logs) {
            if (log.getToolName() != null) {
                counts.merge(log.getToolName(), 1L, Long::sum);
            }
        }
        return counts.entrySet().stream()
                .sorted(Map.Entry.<String, Long>comparingByValue().reversed())
                .map(e -> new ToolUsage(e.getKey(), e.getValue()))
                .toList();
    }
}

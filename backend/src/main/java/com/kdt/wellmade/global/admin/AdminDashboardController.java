package com.kdt.wellmade.global.admin;

import java.time.LocalDate;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.kdt.wellmade.domain.report.PoseReportRepository;
import com.kdt.wellmade.domain.report.ReportStatus;
import com.kdt.wellmade.domain.user.UserRepository;

import lombok.RequiredArgsConstructor;

/** 대시보드 홈 통계. 예전 Thymeleaf AdminController.dashboard()를 JSON REST로 재구현. */
@RestController
@RequestMapping("/api/admin/dashboard")
@RequiredArgsConstructor
public class AdminDashboardController {

    private final UserRepository userRepository;
    private final PoseReportRepository poseReportRepository;

    @GetMapping
    public Map<String, Long> dashboard() {
        return Map.of(
                "totalUsers", userRepository.count(),
                "todaySignups", userRepository.countByCreatedAtAfter(LocalDate.now().atStartOfDay()),
                "pendingReports", poseReportRepository.countByStatus(ReportStatus.PENDING),
                "approvedReports", poseReportRepository.countByStatus(ReportStatus.APPROVED),
                "rejectedReports", poseReportRepository.countByStatus(ReportStatus.REJECTED));
    }
}

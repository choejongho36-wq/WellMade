package com.kdt.wellmade.global.admin;

import java.time.LocalDate;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

import com.kdt.wellmade.domain.report.ReportStatus;
import com.kdt.wellmade.domain.report.PoseReportRepository;
import com.kdt.wellmade.domain.user.UserRepository;

import lombok.RequiredArgsConstructor;

/** 로그인 화면 + 대시보드 홈. 신고 목록/승인/반려는 AdminReportController가 따로 맡는다. */
@Controller
@RequiredArgsConstructor
public class AdminController {

    private final UserRepository userRepository;
    private final PoseReportRepository poseReportRepository;

    @GetMapping("/admin/login")
    public String loginPage() {
        return "admin/login";
    }

    @GetMapping("/admin")
    public String dashboard(Model model) {
        model.addAttribute("totalUsers", userRepository.count());
        model.addAttribute("todaySignups", userRepository.countByCreatedAtAfter(LocalDate.now().atStartOfDay()));
        model.addAttribute("pendingReports", poseReportRepository.countByStatus(ReportStatus.PENDING));
        model.addAttribute("approvedReports", poseReportRepository.countByStatus(ReportStatus.APPROVED));
        model.addAttribute("rejectedReports", poseReportRepository.countByStatus(ReportStatus.REJECTED));
        return "admin/dashboard";
    }
}

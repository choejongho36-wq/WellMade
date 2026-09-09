package com.kdt.wellmade.domain.report;

import java.io.IOException;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;

import lombok.RequiredArgsConstructor;

/**
 * 신고(pose report) 검토 화면. 목록 -> 상세(원본 미리보기 + 판정 스냅샷) -> 승인/반려,
 * 그리고 승인된 것들을 모아 zip으로 내려받는 액티브러닝 export까지 여기서 처리한다.
 */
@Controller
@RequiredArgsConstructor
public class AdminReportController {

    private static final int PAGE_SIZE = 20;

    private final PoseReportService poseReportService;

    @GetMapping("/admin/reports")
    public String list(@RequestParam(value = "status", required = false) ReportStatus status,
                        @RequestParam(value = "page", defaultValue = "0") int page,
                        Model model) {
        Page<PoseReport> reports = poseReportService.list(status, PageRequest.of(page, PAGE_SIZE));
        model.addAttribute("reports", reports);
        model.addAttribute("selectedStatus", status);
        model.addAttribute("statuses", ReportStatus.values());
        return "admin/reports";
    }

    @GetMapping("/admin/reports/{id}")
    public String detail(@PathVariable Long id, Model model) {
        PoseReport report = poseReportService.get(id);
        model.addAttribute("report", report);
        model.addAttribute("presignedUrl", poseReportService.presignedUrlFor(report));
        return "admin/report-detail";
    }

    @PostMapping("/admin/reports/{id}/approve")
    public String approve(@PathVariable Long id, Authentication authentication) {
        poseReportService.approve(id, authentication.getName());
        return "redirect:/admin/reports/" + id;
    }

    @PostMapping("/admin/reports/{id}/reject")
    public String reject(@PathVariable Long id, Authentication authentication) {
        poseReportService.reject(id, authentication.getName());
        return "redirect:/admin/reports";
    }

    /** 승인된 신고 전체 + manifest.json + README.txt를 zip 하나로 내려준다(액티브러닝 오프라인 처리용). */
    @GetMapping("/admin/reports/export")
    @ResponseBody
    public ResponseEntity<byte[]> exportApproved() throws IOException {
        byte[] zip = poseReportService.exportApprovedZip();
        return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=\"wellmade-active-learning-export.zip\"")
                .header(HttpHeaders.CONTENT_TYPE, "application/zip")
                .body(zip);
    }
}

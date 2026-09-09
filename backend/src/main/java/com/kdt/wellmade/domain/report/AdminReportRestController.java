package com.kdt.wellmade.domain.report;

import java.io.IOException;
import java.time.LocalDateTime;
import java.util.List;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import lombok.RequiredArgsConstructor;

/**
 * 신고(pose report) 검토 REST API. 예전 Thymeleaf AdminReportController(목록/상세 화면 +
 * 승인/반려 폼 제출)를 JSON 엔드포인트로 재구현한 것 — 실제 비즈니스 로직(PoseReportService)은
 * 그대로 재사용하고, 화면 렌더링 대신 데이터만 내려준다.
 */
@RestController
@RequestMapping("/api/admin/reports")
@RequiredArgsConstructor
public class AdminReportRestController {

    private static final int PAGE_SIZE = 20;

    private final PoseReportService poseReportService;

    public record ReportListItem(
            Long id, String sourceType, String reasonCategory, String reasonDetail,
            String status, LocalDateTime createdAt) {
        static ReportListItem from(PoseReport r) {
            return new ReportListItem(r.getId(), r.getSourceType().name(), r.getReasonCategory().name(),
                    r.getReasonDetail(), r.getStatus().name(), r.getCreatedAt());
        }
    }

    public record ReportListResponse(List<ReportListItem> content, int page, int totalPages, long totalElements) {
    }

    @GetMapping
    public ReportListResponse list(@RequestParam(value = "status", required = false) ReportStatus status,
                                    @RequestParam(value = "page", defaultValue = "0") int page) {
        Page<PoseReport> reports = poseReportService.list(status, PageRequest.of(page, PAGE_SIZE));
        return new ReportListResponse(
                reports.getContent().stream().map(ReportListItem::from).toList(),
                reports.getNumber(), reports.getTotalPages(), reports.getTotalElements());
    }

    public record ReportDetailResponse(
            Long id, String sourceType, String reasonCategory, String reasonDetail, String status,
            String aiJudgmentSnapshot, LocalDateTime createdAt, String reviewedBy, LocalDateTime reviewedAt,
            String presignedUrl) {
    }

    @GetMapping("/{id}")
    public ReportDetailResponse detail(@PathVariable Long id) {
        PoseReport report = poseReportService.get(id);
        return new ReportDetailResponse(
                report.getId(), report.getSourceType().name(), report.getReasonCategory().name(),
                report.getReasonDetail(), report.getStatus().name(), report.getAiJudgmentSnapshot(),
                report.getCreatedAt(), report.getReviewedBy(), report.getReviewedAt(),
                poseReportService.presignedUrlFor(report));
    }

    @PostMapping("/{id}/approve")
    public ResponseEntity<Void> approve(@PathVariable Long id, Authentication authentication) {
        poseReportService.approve(id, authentication.getName());
        return ResponseEntity.noContent().build();
    }

    @PostMapping("/{id}/reject")
    public ResponseEntity<Void> reject(@PathVariable Long id, Authentication authentication) {
        poseReportService.reject(id, authentication.getName());
        return ResponseEntity.noContent().build();
    }

    /** 승인된 신고 전체 + manifest.json + README.txt를 zip 하나로 내려준다(액티브러닝 오프라인 처리용). */
    @GetMapping("/export")
    public ResponseEntity<byte[]> exportApproved() throws IOException {
        byte[] zip = poseReportService.exportApprovedZip();
        return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=\"wellmade-active-learning-export.zip\"")
                .header(HttpHeaders.CONTENT_TYPE, "application/zip")
                .body(zip);
    }
}

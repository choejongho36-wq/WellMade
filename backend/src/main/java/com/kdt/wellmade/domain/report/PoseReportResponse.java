package com.kdt.wellmade.domain.report;

import java.time.LocalDateTime;

/** 관리자 화면(및 필요시 API)에 내려줄 신고 건 요약. 원본 파일은 presignedUrl로만 노출한다(S3 key 직접 노출 안 함). */
public record PoseReportResponse(
        Long id,
        Long userId,
        ReportSourceType sourceType,
        String sourceId,
        String presignedUrl,
        String aiJudgmentSnapshot,
        ReportReasonCategory reasonCategory,
        String reasonDetail,
        ReportStatus status,
        String reviewedBy,
        LocalDateTime reviewedAt,
        LocalDateTime createdAt
) {
    public static PoseReportResponse from(PoseReport report, String presignedUrl) {
        return new PoseReportResponse(
                report.getId(),
                report.getUser().getId(),
                report.getSourceType(),
                report.getSourceId(),
                presignedUrl,
                report.getAiJudgmentSnapshot(),
                report.getReasonCategory(),
                report.getReasonDetail(),
                report.getStatus(),
                report.getReviewedBy(),
                report.getReviewedAt(),
                report.getCreatedAt()
        );
    }
}

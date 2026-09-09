package com.kdt.wellmade.domain.report;

import java.time.LocalDateTime;

import com.kdt.wellmade.domain.user.User;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.Lob;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;
import lombok.AccessLevel;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

/**
 * 사진측정/세션리포트 화면에서 사용자가 "이 판정이 이상해요"로 신고한 건.
 * 원본 미디어(사진/영상)는 DB가 아니라 S3에 저장하고, 여기엔 S3 key만 들고 있다.
 * 승인(APPROVED)돼도 서버가 좌표추출/템플릿 재계산을 자동으로 하지 않는다 — 반자동 원칙
 * (claude/wellmade-squat-criteria-checklist-2026-08-27-addendum.md 참고): 관리자가 승인한
 * 건들을 모아 관리자가 로컬에서 오프라인 스크립트로 처리한 뒤 사람이 검토해 템플릿에 반영한다.
 */
@Entity
@Table(name = "pose_reports")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class PoseReport {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "user_id", nullable = false)
    private User user;

    @Enumerated(EnumType.STRING)
    @Column(name = "source_type", nullable = false, length = 20)
    private ReportSourceType sourceType;

    // 원본 세션 ID(SESSION) 또는 사진측정 캡처를 식별할 값(PHOTO). 참고용이라 다른 테이블 FK로는 안 묶는다.
    @Column(name = "source_id", length = 100)
    private String sourceId;

    @Column(name = "s3_key", nullable = false, length = 500)
    private String s3Key;

    // 신고 당시 AI가 내렸던 판정 결과 스냅샷(JSON 문자열 그대로 보관) — 나중에 검토/템플릿화할 때
    // "이 신고가 왜 접수됐는지"를 재구성할 수 있어야 해서, 신고 시점 값을 그대로 얼려둔다.
    @Lob
    @Column(name = "ai_judgment_snapshot")
    private String aiJudgmentSnapshot;

    @Enumerated(EnumType.STRING)
    @Column(name = "reason_category", nullable = false, length = 30)
    private ReportReasonCategory reasonCategory;

    // OTHER 선택 시 사용자가 직접 적은 사유
    @Column(name = "reason_detail", length = 500)
    private String reasonDetail;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private ReportStatus status;

    @Column(name = "reviewed_by", length = 100)
    private String reviewedBy;

    @Column(name = "reviewed_at")
    private LocalDateTime reviewedAt;

    @Column(name = "created_at", nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @Builder
    public PoseReport(User user, ReportSourceType sourceType, String sourceId, String s3Key,
                       String aiJudgmentSnapshot, ReportReasonCategory reasonCategory, String reasonDetail) {
        this.user = user;
        this.sourceType = sourceType;
        this.sourceId = sourceId;
        this.s3Key = s3Key;
        this.aiJudgmentSnapshot = aiJudgmentSnapshot;
        this.reasonCategory = reasonCategory;
        this.reasonDetail = reasonDetail;
        this.status = ReportStatus.PENDING;
    }

    public void approve(String adminLoginId) {
        this.status = ReportStatus.APPROVED;
        this.reviewedBy = adminLoginId;
        this.reviewedAt = LocalDateTime.now();
    }

    public void reject(String adminLoginId) {
        this.status = ReportStatus.REJECTED;
        this.reviewedBy = adminLoginId;
        this.reviewedAt = LocalDateTime.now();
    }

    @PrePersist
    protected void onCreate() {
        this.createdAt = LocalDateTime.now();
    }
}

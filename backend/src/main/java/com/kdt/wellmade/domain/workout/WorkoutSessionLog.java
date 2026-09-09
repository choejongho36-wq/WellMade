package com.kdt.wellmade.domain.workout;

import java.time.LocalDateTime;

import com.kdt.wellmade.domain.report.ReportSourceType;
import com.kdt.wellmade.domain.user.User;
import com.kdt.wellmade.global.time.AppTime;

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
 * 실시간 세션(SESSION)·사진측정(PHOTO) 코칭이 끝날 때마다 프론트가 남기는 결과 요약 한 건.
 * AI 판정 자체는 프론트/AI 서버(FastAPI)에서 끝나고, 여기엔 관리자 대시보드 집계에 필요한
 * 요약값만 온다 — 원본 프레임/좌표는 저장하지 않는다(신고된 건만 PoseReport로 별도 보관).
 * sourceType은 PoseReport와 같은 개념이라 그 enum(ReportSourceType)을 그대로 쓴다.
 */
@Entity
@Table(name = "workout_session_logs")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class WorkoutSessionLog {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "user_id", nullable = false)
    private User user;

    @Enumerated(EnumType.STRING)
    @Column(name = "source_type", nullable = false, length = 20)
    private ReportSourceType sourceType;

    @Column(name = "result_normal", nullable = false)
    private boolean resultNormal;

    // SESSION에서만 옴(PHOTO는 반복 횟수 개념이 없어 null)
    @Column(name = "total_reps")
    private Integer totalReps;

    @Column(name = "abnormal_reps")
    private Integer abnormalReps;

    // 이슈 부위별 발생 횟수를 JSON 객체 문자열로 그대로 보관 (예: {"KNEE":2,"HIP":1}).
    // 집계 시점에 부위 종류가 늘어도 스키마 변경 없이 담을 수 있어 이렇게 뒀다.
    @Lob
    @Column(name = "issue_counts")
    private String issueCounts;

    @Column(name = "created_at", nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @Builder
    public WorkoutSessionLog(User user, ReportSourceType sourceType, boolean resultNormal,
                              Integer totalReps, Integer abnormalReps, String issueCounts) {
        this.user = user;
        this.sourceType = sourceType;
        this.resultNormal = resultNormal;
        this.totalReps = totalReps;
        this.abnormalReps = abnormalReps;
        this.issueCounts = issueCounts;
    }

    @PrePersist
    protected void onCreate() {
        this.createdAt = AppTime.now();
    }
}

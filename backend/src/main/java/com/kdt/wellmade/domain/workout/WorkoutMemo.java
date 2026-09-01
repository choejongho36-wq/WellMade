package com.kdt.wellmade.domain.workout;

import java.time.LocalDate;
import java.time.LocalDateTime;

import com.kdt.wellmade.domain.user.User;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import lombok.AccessLevel;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

/**
 * 날짜별 운동 메모. 식단은 끼니마다 여러 건이지만 운동 메모는 하루에 한 장이라
 * (user_id, memo_date)에 유니크를 걸고 같은 날 저장은 덮어쓴다.
 *
 * 운동을 종목·세트·중량으로 구조화하지 않고 자유 텍스트로 둔 이유: 사용자가 뭘 어떻게 적을지
 * 아직 모르는데 스키마를 먼저 고정하면 안 맞는 칸을 억지로 채우게 된다. 실제로 어떻게 쓰는지
 * 보고 나서 구조화해도 늦지 않다.
 */
@Entity
@Table(
        name = "workout_memos",
        uniqueConstraints = @UniqueConstraint(name = "uk_workout_memo_user_date",
                columnNames = {"user_id", "memo_date"})
)
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class WorkoutMemo {

    /** 자유 텍스트라 상한만 둔다. 화면에서도 같은 값으로 막는다(DietPage.jsx) */
    public static final int MAX_LENGTH = 1000;

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "user_id", nullable = false)
    private User user;

    @Column(name = "memo_date", nullable = false)
    private LocalDate memoDate;

    @Column(nullable = false, length = MAX_LENGTH)
    private String content;

    @Column(name = "updated_at", nullable = false)
    private LocalDateTime updatedAt;

    @Builder
    private WorkoutMemo(User user, LocalDate memoDate, String content) {
        this.user = user;
        this.memoDate = memoDate;
        this.content = content;
    }

    public void updateContent(String content) {
        this.content = content;
    }

    @PrePersist
    @PreUpdate
    void touch() {
        this.updatedAt = LocalDateTime.now();
    }
}

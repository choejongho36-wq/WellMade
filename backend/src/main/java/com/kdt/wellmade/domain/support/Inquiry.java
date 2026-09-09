package com.kdt.wellmade.domain.support;

import java.time.LocalDateTime;

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
 * 고객센터 1:1 문의 게시판 글 한 건. 제목/분류는 전체 회원에게 공개되고, 비밀글(secret)이면
 * 본문·답변은 작성자 본인과 관리자만 볼 수 있다 - 노출 여부는 컨트롤러/서비스가 조회 시점에
 * 가린다(엔티티 자체는 그냥 값을 들고 있을 뿐).
 */
@Entity
@Table(name = "inquiries")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class Inquiry {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "user_id", nullable = false)
    private User user;

    @Column(nullable = false, length = 100)
    private String title;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private InquiryCategory category;

    @Lob
    @Column(nullable = false)
    private String content;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private InquiryStatus status;

    @Lob
    private String answer;

    @Column(nullable = false)
    private boolean secret;

    @Column(name = "created_at", nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @Column(name = "answered_at")
    private LocalDateTime answeredAt;

    @Builder
    public Inquiry(User user, String title, InquiryCategory category, String content, boolean secret) {
        this.user = user;
        this.title = title;
        this.category = category;
        this.content = content;
        this.secret = secret;
        this.status = InquiryStatus.PENDING;
    }

    public void update(String title, InquiryCategory category, String content, boolean secret) {
        this.title = title;
        this.category = category;
        this.content = content;
        this.secret = secret;
    }

    public void answer(String answer) {
        this.answer = answer;
        this.status = InquiryStatus.ANSWERED;
        this.answeredAt = AppTime.now();
    }

    public void clearAnswer() {
        this.answer = null;
        this.status = InquiryStatus.PENDING;
        this.answeredAt = null;
    }

    @PrePersist
    protected void onCreate() {
        this.createdAt = AppTime.now();
    }
}

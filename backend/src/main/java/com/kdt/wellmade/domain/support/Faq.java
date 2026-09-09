package com.kdt.wellmade.domain.support;

import java.time.LocalDateTime;

import com.kdt.wellmade.global.time.AppTime;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Lob;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;
import lombok.AccessLevel;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

/**
 * 고객센터 FAQ 한 건. displayOrder가 작을수록 목록 위쪽에 노출된다(관리자가 직접 정한 순서) -
 * 값이 같으면 최신순으로 정렬.
 */
@Entity
@Table(name = "faqs")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class Faq {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 200)
    private String question;

    @Lob
    @Column(nullable = false)
    private String answer;

    @Column(name = "display_order", nullable = false)
    private int displayOrder;

    @Column(name = "created_at", nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @Builder
    public Faq(String question, String answer, int displayOrder) {
        this.question = question;
        this.answer = answer;
        this.displayOrder = displayOrder;
    }

    public void update(String question, String answer, int displayOrder) {
        this.question = question;
        this.answer = answer;
        this.displayOrder = displayOrder;
    }

    @PrePersist
    protected void onCreate() {
        this.createdAt = AppTime.now();
    }
}

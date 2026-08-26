package com.kdt.wellmade.domain.chat;

import java.time.LocalDateTime;

import com.kdt.wellmade.domain.user.User;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
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
 * 챗봇 대화 한 턴(사용자 발화 또는 모델 응답)을 저장하는 엔티티.
 *
 * 예전엔 대화 이력이 프론트 useState에만 있었고, 서버는 클라이언트가 매번 보내는 배열을 그대로
 * 신뢰했음(role 위조 가능, 새로고침하면 이력 소실). 이제 서버가 진실 소스를 갖고, 클라이언트는
 * 새로 보낸 사용자 메시지 한 개만 전달하면 됨.
 */
@Entity
@Table(name = "chat_messages")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class ChatMessageEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "user_id", nullable = false)
    private User user;

    // "user" / "assistant" - Ollama가 그대로 쓰는 값이라 굳이 enum으로 감싸지 않고 문자열로 저장
    @Column(nullable = false, length = 20)
    private String role;

    @Lob
    @Column(nullable = false, columnDefinition = "TEXT")
    private String content;

    @Column(name = "created_at", nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @Builder
    public ChatMessageEntity(User user, String role, String content) {
        this.user = user;
        this.role = role;
        this.content = content;
    }

    @PrePersist
    protected void onCreate() {
        this.createdAt = LocalDateTime.now();
    }
}

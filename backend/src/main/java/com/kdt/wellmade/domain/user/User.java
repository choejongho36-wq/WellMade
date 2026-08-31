package com.kdt.wellmade.domain.user;


import java.time.LocalDateTime;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import lombok.AccessLevel;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Entity
@Table(name = "users", uniqueConstraints = {
    @UniqueConstraint(columnNames = {"provider", "provider_id"})
})
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class User {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private Provider provider; //Google , Kakao , Naver

    @Column(name = "provider_id", nullable = false, length = 100)
    private String providerId;

    @Column(length = 255)
    private String email;

    // 탈퇴 시 소셜 제공자 연동 해제(unlink)에 쓸 마지막 로그인 시점의 access token.
    // 신원확인용으로만 쓰고 평소엔 참조 안 함. 만료됐으면 unlink가 실패할 뿐 탈퇴는 진행됨.
    @Column(name = "social_access_token", length = 1000)
    private String socialAccessToken;

    @Column(name = "created_at", nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @Column(name = "updated_at", nullable = false)
    private LocalDateTime updatedAt;

    @Builder
    public User(Provider provider, String providerId, String email){
        this.provider = provider;
        this.providerId = providerId;
        this.email = email;
    }

    public void updateSocialAccessToken(String socialAccessToken){
        this.socialAccessToken = socialAccessToken;
    }

    @PrePersist
    protected void onCreate(){
        this.createdAt = LocalDateTime.now();
        this.updatedAt = LocalDateTime.now();
    }

    @PreUpdate
    protected void onUpdate(){
        this.updatedAt = LocalDateTime.now();
    }
 
}

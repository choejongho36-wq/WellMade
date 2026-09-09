package com.kdt.wellmade.global.admin;

import java.time.LocalDateTime;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import lombok.AccessLevel;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

/**
 * /admin 전용 로그인 계정. WellMade의 User는 OAuth2 전용(비밀번호 없음)이라 관리자 계정을
 * 그 위에 얹을 수 없어서 별도 테이블로 분리했다(Roomie는 User에 role을 얹어 재사용했지만,
 * WellMade User는 로그인아이디/비밀번호 자체가 없어 같은 방식을 쓸 수 없었음).
 */
@Entity
@Table(name = "admin_accounts", uniqueConstraints = {
        @UniqueConstraint(columnNames = "login_id")
})
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class AdminAccount {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "login_id", nullable = false, length = 100)
    private String loginId;

    // BCrypt 인코딩된 값만 저장한다 — 평문 저장 금지
    @Column(nullable = false, length = 100)
    private String password;

    @Column(nullable = false, length = 50)
    private String name;

    @Column(name = "created_at", nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @Builder
    public AdminAccount(String loginId, String password, String name) {
        this.loginId = loginId;
        this.password = password;
        this.name = name;
    }

    @PrePersist
    protected void onCreate() {
        this.createdAt = LocalDateTime.now();
    }
}

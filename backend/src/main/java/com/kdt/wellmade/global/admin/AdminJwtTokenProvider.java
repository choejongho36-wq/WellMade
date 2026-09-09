package com.kdt.wellmade.global.admin;

import java.nio.charset.StandardCharsets;
import java.util.Date;

import javax.crypto.SecretKey;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.JwtException;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;

/**
 * 관리자(admin) 전용 JWT. 일반 회원 JWT(global.security.JwtTokenProvider)와 서명 키를
 * 완전히 분리한다 — 회원 토큰이 유출/위조돼도 이 키가 달라 admin 권한을 절대 얻을 수 없게
 * 하기 위함(admin_accounts를 User와 별도 테이블로 분리해둔 기존 원칙을 토큰 체계에도 그대로
 * 이어감). 관리자 대시보드를 백엔드 Thymeleaf 세션 로그인에서 프론트(React) + 이 토큰
 * 기반으로 전환하며 신설.
 */
@Component
public class AdminJwtTokenProvider {

    private final SecretKey key;
    private final long accessTokenValidity;

    public AdminJwtTokenProvider(
            @Value("${admin.jwt.secret}") String secret,
            @Value("${admin.jwt.access-token-validity}") long accessTokenValidity) {
        this.key = Keys.hmacShaKeyFor(secret.getBytes(StandardCharsets.UTF_8));
        this.accessTokenValidity = accessTokenValidity;
    }

    public long getAccessTokenValidity() {
        return accessTokenValidity;
    }

    public String generateToken(String loginId) {
        Date now = new Date();
        Date expiry = new Date(now.getTime() + accessTokenValidity);
        return Jwts.builder()
                .subject(loginId)
                .claim("role", "ADMIN")
                .issuedAt(now)
                .expiration(expiry)
                .signWith(key)
                .compact();
    }

    public boolean validateToken(String token) {
        try {
            Claims claims = Jwts.parser().verifyWith(key).build().parseSignedClaims(token).getPayload();
            return "ADMIN".equals(claims.get("role", String.class));
        } catch (JwtException | IllegalArgumentException e) {
            return false;
        }
    }

    public String getLoginId(String token) {
        Claims claims = Jwts.parser().verifyWith(key).build().parseSignedClaims(token).getPayload();
        return claims.getSubject();
    }
}

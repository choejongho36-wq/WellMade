package com.kdt.wellmade.global.admin;

import java.io.IOException;
import java.util.List;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;

/**
 * httpOnly 쿠키(admin_token)에서 관리자 JWT를 읽어 인증한다 — 일반 회원 JWT 필터
 * (Authorization 헤더 + localStorage 기반)와 완전히 분리된 별도 경로다. 토큰을 localStorage가
 * 아니라 httpOnly 쿠키에 두는 이유: XSS가 나더라도 JS가 이 토큰을 읽어갈 수 없게 하기 위함
 * (관리자 계정은 신고 승인/반려·개인정보 통계 등 권한이 커서 더 엄격한 보관 방식을 쓴다).
 */
@Component
@RequiredArgsConstructor
public class AdminJwtAuthenticationFilter extends OncePerRequestFilter {

    public static final String COOKIE_NAME = "admin_token";

    private final AdminJwtTokenProvider adminJwtTokenProvider;

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
            throws ServletException, IOException {
        Cookie[] cookies = request.getCookies();
        if (cookies != null) {
            for (Cookie cookie : cookies) {
                if (COOKIE_NAME.equals(cookie.getName()) && adminJwtTokenProvider.validateToken(cookie.getValue())) {
                    String loginId = adminJwtTokenProvider.getLoginId(cookie.getValue());
                    Authentication authentication = new UsernamePasswordAuthenticationToken(
                            loginId, null, List.of(new SimpleGrantedAuthority("ROLE_ADMIN")));
                    SecurityContextHolder.getContext().setAuthentication(authentication);
                    break;
                }
            }
        }
        filterChain.doFilter(request, response);
    }
}

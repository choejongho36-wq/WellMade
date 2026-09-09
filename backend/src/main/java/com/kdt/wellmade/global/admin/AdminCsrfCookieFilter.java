package com.kdt.wellmade.global.admin;

import java.io.IOException;

import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.filter.OncePerRequestFilter;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

/**
 * XSRF-TOKEN 쿠키를 매 요청마다 강제로 로드시켜 응답에 항상 실리게 한다 — Spring Security의
 * CsrfToken은 기본적으로 지연 로딩이라, 뭔가가 명시적으로 읽지 않으면 쿠키가 응답에 안 실릴
 * 수 있다(SPA 프론트가 로그인 전에도 이 쿠키를 미리 읽어 X-XSRF-TOKEN 헤더로 되돌려 보내야
 * 하므로 필요). Spring 공식 "CSRF for SPA" 가이드와 동일한 패턴.
 */
public class AdminCsrfCookieFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
            throws ServletException, IOException {
        CsrfToken csrfToken = (CsrfToken) request.getAttribute(CsrfToken.class.getName());
        if (csrfToken != null) {
            csrfToken.getToken();
        }
        filterChain.doFilter(request, response);
    }
}

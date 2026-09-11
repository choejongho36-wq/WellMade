package com.kdt.wellmade.global.admin;

import java.time.Duration;
import java.util.Map;

import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import lombok.RequiredArgsConstructor;

/**
 * 관리자 로그인/로그아웃/세션 확인. 예전 세션 기반 폼 로그인(SecurityConfig의
 * formLogin)을 걷어내고 JWT 쿠키 발급 방식으로 대체했다 — 아이디/비밀번호는 admin_accounts
 * 테이블에서 직접 대조하고(DaoAuthenticationProvider 대신 PasswordEncoder를 여기서 바로
 * 씀), 성공하면 httpOnly 쿠키(admin_token)에 서명된 JWT를 담아 내려준다.
 */
@RestController
@RequestMapping("/api/admin/auth")
@RequiredArgsConstructor
public class AdminAuthController {

    private final AdminAccountRepository adminAccountRepository;
    private final PasswordEncoder passwordEncoder;
    private final AdminJwtTokenProvider adminJwtTokenProvider;
    private final AdminLoginAttemptGuard loginAttemptGuard;

    public record LoginRequest(String loginId, String password) {
    }

    @PostMapping("/login")
    public ResponseEntity<Map<String, String>> login(@RequestBody LoginRequest request) {
        String loginId = request.loginId() == null ? "" : request.loginId().trim();
        String password = request.password() == null ? "" : request.password();

        if (loginAttemptGuard.isLocked(loginId)) {
            return ResponseEntity.status(429)
                    .body(Map.of("message", "로그인 시도가 너무 많습니다. 잠시 후 다시 시도해주세요."));
        }

        boolean authenticated = adminAccountRepository.findByLoginId(loginId)
                .filter(account -> passwordEncoder.matches(password, account.getPassword()))
                .isPresent();

        if (!authenticated) {
            loginAttemptGuard.onFailure(loginId);
            // 아이디/비밀번호 중 어느 쪽이 틀렸는지는 알려주지 않는다(계정 존재 여부 노출 방지).
            return ResponseEntity.status(401)
                    .body(Map.of("message", "아이디 또는 비밀번호가 올바르지 않습니다."));
        }
        loginAttemptGuard.onSuccess(loginId);

        String token = adminJwtTokenProvider.generateToken(loginId);
        ResponseCookie cookie = buildCookie(token, adminJwtTokenProvider.getAccessTokenValidity());

        return ResponseEntity.ok()
                .header("Set-Cookie", cookie.toString())
                .body(Map.of("loginId", loginId));
    }

    @PostMapping("/logout")
    public ResponseEntity<Void> logout() {
        ResponseCookie cookie = buildCookie("", 0);
        return ResponseEntity.ok().header("Set-Cookie", cookie.toString()).build();
    }

    @GetMapping("/me")
    public ResponseEntity<Map<String, String>> me(Authentication authentication) {
        if (authentication == null) {
            return ResponseEntity.status(401).build();
        }
        return ResponseEntity.ok(Map.of("loginId", authentication.getName()));
    }

    private ResponseCookie buildCookie(String token, long maxAgeMs) {
        return ResponseCookie.from(AdminJwtAuthenticationFilter.COOKIE_NAME, token)
                .httpOnly(true)
                .secure(true)
                .sameSite("Strict")
                .path("/")
                .maxAge(Duration.ofMillis(maxAgeMs))
                .build();
    }
}

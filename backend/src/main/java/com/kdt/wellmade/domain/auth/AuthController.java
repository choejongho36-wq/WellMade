package com.kdt.wellmade.domain.auth;

import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.kdt.wellmade.global.security.JwtTokenProvider;
import com.kdt.wellmade.global.security.OAuth2CodeStore;

import lombok.RequiredArgsConstructor;


@RestController
@RequestMapping("/api/auth")
@RequiredArgsConstructor
public class AuthController {
    private final OAuth2CodeStore oAuth2CodeStore;
    private final JwtTokenProvider jwtTokenProvider;

    public record TokenExchangeRequest(String code){}

    @PostMapping("/token")
    public ResponseEntity<?> exchangeToken(@RequestBody TokenExchangeRequest request) {
        Long userId = oAuth2CodeStore.consume(request.code());
        
        if (userId == null) {
            return ResponseEntity.badRequest().body(Map.of("message", "유효하지 않거나 만료된 코드입니다."));
        }
        String token = jwtTokenProvider.generateToken(userId);
        return ResponseEntity.ok(Map.of("accessToken", token));
    }
    
}

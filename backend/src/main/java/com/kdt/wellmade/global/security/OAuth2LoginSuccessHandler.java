package com.kdt.wellmade.global.security;

import java.io.IOException;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.authentication.SimpleUrlAuthenticationSuccessHandler;
import org.springframework.stereotype.Component;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;

@Component
@RequiredArgsConstructor
public class OAuth2LoginSuccessHandler extends SimpleUrlAuthenticationSuccessHandler {

    private final OAuth2CodeStore oAuth2CodeStore;
    
    @Value("${app.oauth2.redirect-uri:http://localhost:5173/oauth/redirect}")
    private String redirectUrl;

    private Long extractUserId(Authentication authentication) {
    CustomOAuth2User principal = (CustomOAuth2User) authentication.getPrincipal();
    return principal.getUserId();
}


    @Override
    public void onAuthenticationSuccess(HttpServletRequest request, HttpServletResponse response,
            Authentication authentication) throws IOException {
        Long userId = extractUserId(authentication);

        String code = oAuth2CodeStore.issue(userId);
        String targetUrl = redirectUrl + "?code=" + code;

        getRedirectStrategy().sendRedirect(request, response, targetUrl);
    }
}

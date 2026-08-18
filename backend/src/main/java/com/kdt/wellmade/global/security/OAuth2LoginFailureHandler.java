package com.kdt.wellmade.global.security;

import java.io.IOException;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.web.authentication.AuthenticationFailureHandler;
import org.springframework.stereotype.Component;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

@Component
public class OAuth2LoginFailureHandler implements AuthenticationFailureHandler {

    @Value("${app.oauth2.redirect-uri:http://localhost:5173/oauth/redirect}")
    private String redirectUri;

    @Override
    public void onAuthenticationFailure(HttpServletRequest request, HttpServletResponse response,
            AuthenticationException exception) throws IOException {
        String errorCode = exception instanceof OAuth2AuthenticationException oAuth2Exception
            ? oAuth2Exception.getError().getErrorCode()
            : "LOGIN_FAILED";

        String encodedError = URLEncoder.encode(errorCode, StandardCharsets.UTF_8);
        response.sendRedirect(redirectUri + "?error=" + encodedError);
    }
}

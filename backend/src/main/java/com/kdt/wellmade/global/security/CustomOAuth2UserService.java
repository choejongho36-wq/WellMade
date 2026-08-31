package com.kdt.wellmade.global.security;

import java.util.Locale;
import java.util.Map;

import org.springframework.security.oauth2.client.userinfo.DefaultOAuth2UserService;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserRequest;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.user.OAuth2User;
import org.springframework.stereotype.Service;

import com.kdt.wellmade.domain.user.Provider;
import com.kdt.wellmade.domain.user.User;
import com.kdt.wellmade.domain.user.UserService;

import lombok.RequiredArgsConstructor;

@Service
@RequiredArgsConstructor
public class CustomOAuth2UserService extends DefaultOAuth2UserService {

    private final UserService userService;

    @Override
    public OAuth2User loadUser(OAuth2UserRequest userRequest) throws OAuth2AuthenticationException {
        OAuth2User oAuth2User = super.loadUser(userRequest);

        Provider provider = Provider.valueOf(
            userRequest.getClientRegistration().getRegistrationId().toUpperCase(Locale.ROOT));

        Map<String, Object> attributes = oAuth2User.getAttributes();
        String providerId = extractProviderId(provider, attributes);
        String email = extractEmail(provider, attributes);

        User user = userService.loginOrRegister(provider, providerId, email,
            userRequest.getAccessToken().getTokenValue());
        return new CustomOAuth2User(user.getId(), attributes, nameAttributeKey(provider));
    }

    // ponytail: 카카오/네이버는 application.yml에 client 등록 전 등록 시 user-name-attribute 값도 아래 키와 맞춰야 함.
    private String extractProviderId(Provider provider, Map<String, Object> attributes) {
        return switch (provider) {
            case GOOGLE -> String.valueOf(attributes.get("sub"));
            case KAKAO -> String.valueOf(attributes.get("id"));
            case NAVER -> String.valueOf(responseAttributes(attributes).get("id"));
        };
    }

    private String extractEmail(Provider provider, Map<String, Object> attributes) {
        String email = switch (provider) {
            case GOOGLE -> (String) attributes.get("email");
            case KAKAO -> {
                Map<?, ?> kakaoAccount = (Map<?, ?>) attributes.get("kakao_account");
                yield kakaoAccount == null ? null : (String) kakaoAccount.get("email");
            }
            case NAVER -> (String) responseAttributes(attributes).get("email");
        };

        if (email == null) {
            throw new OAuth2AuthenticationException(
                new OAuth2Error("EMAIL_NOT_CONSENTED"), "이메일 제공에 동의해야 로그인할 수 있습니다.");
        }
        return email;
    }

    private String nameAttributeKey(Provider provider) {
        return switch (provider) {
            case GOOGLE -> "sub";
            case KAKAO -> "id";
            case NAVER -> "response";
        };
    }

    private Map<?, ?> responseAttributes(Map<String, Object> attributes) {
        return (Map<?, ?>) attributes.get("response");
    }
}

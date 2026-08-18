package com.kdt.wellmade.global.security;

import java.util.Locale;
import java.util.Map;

import org.springframework.security.oauth2.client.userinfo.DefaultOAuth2UserService;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserRequest;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.user.OAuth2User;
import org.springframework.stereotype.Service;

import com.kdt.wellmade.domain.user.Provider;
import com.kdt.wellmade.domain.user.User;
import com.kdt.wellmade.domain.user.UserService;

import lombok.RequiredArgsConstructor;

// ponytail: 구글의 "sub"/"email" 속성명만 처리. 카카오/네이버 붙일 때 registrationId별 매핑 필요.
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
        String providerId = String.valueOf(attributes.get("sub"));
        String email = (String) attributes.get("email");

        User user = userService.loginOrRegister(provider, providerId, email);

        return new CustomOAuth2User(user.getId(), attributes, "sub");
    }
}

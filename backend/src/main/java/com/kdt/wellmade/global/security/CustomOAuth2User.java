package com.kdt.wellmade.global.security;

import java.util.Collection;
import java.util.List;
import java.util.Map;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.user.OAuth2User;

public class CustomOAuth2User implements OAuth2User {

    private final Long userId;
    private final Map<String, Object> attributes;
    private final String nameAttributeKey;

    public CustomOAuth2User(Long userId, Map<String, Object> attributes, String nameAttributeKey) {
        this.userId = userId;
        this.attributes = attributes;
        this.nameAttributeKey = nameAttributeKey;
    }

    public Long getUserId() {
        return userId;
    }

    @Override
    public Map<String, Object> getAttributes() {
        return attributes;
    }

    @Override
    public Collection<? extends GrantedAuthority> getAuthorities() {
        return List.of(new SimpleGrantedAuthority("ROLE_USER"));
    }

    @Override
    public String getName() {
        return String.valueOf(attributes.get(nameAttributeKey));
    }
}

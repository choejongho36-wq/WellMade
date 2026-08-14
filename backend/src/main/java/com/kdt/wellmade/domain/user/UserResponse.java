package com.kdt.wellmade.domain.user;

import java.time.LocalDateTime;

public record UserResponse(Long id, String email, Provider provider, LocalDateTime createdAt) {
    public static UserResponse from(User user) {
        return new UserResponse(user.getId(), user.getEmail(), user.getProvider(), user.getCreatedAt());
    }
}

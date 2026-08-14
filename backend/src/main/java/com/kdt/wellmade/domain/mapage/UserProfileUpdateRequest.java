package com.kdt.wellmade.domain.mapage;

public record UserProfileUpdateRequest(String name, String profileImageUrl, Goal goal) {
}

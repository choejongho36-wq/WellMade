package com.kdt.wellmade.domain.mapage;

public record UserProfileResponse(String name, String profileImageUrl, Goal goal) {

    public static UserProfileResponse from(UserProfile profile) {
        return new UserProfileResponse(profile.getName(), profile.getProfileImageUrl(), profile.getGoal());
    }
}

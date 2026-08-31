package com.kdt.wellmade.domain.mapage;

public record UserProfileResponse(
        String name,
        String profileImageUrl,
        Goal goal,
        Gender gender,
        Double heightCm,
        Integer birthYear) {

    public static UserProfileResponse from(UserProfile profile) {
        return new UserProfileResponse(
                profile.getName(),
                profile.getProfileImageUrl(),
                profile.getGoal(),
                profile.getGender(),
                profile.getHeightCm(),
                profile.getBirthYear());
    }
}

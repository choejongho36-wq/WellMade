package com.kdt.wellmade.domain.mapage;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.kdt.wellmade.domain.user.User;
import com.kdt.wellmade.domain.user.UserService;

import lombok.RequiredArgsConstructor;

@RestController
@RequestMapping("/api/users/me/profile")
@RequiredArgsConstructor
public class UserProfileController {
    private final UserProfileService userProfileService;
    private final UserService userService;

    @GetMapping
    public UserProfileResponse getMyProfile(@AuthenticationPrincipal Long userId) {
        User user = userService.getUser(userId);
        return UserProfileResponse.from(userProfileService.getProfile(user));
    }

    @PutMapping
    public void updateMyProfile(@AuthenticationPrincipal Long userId, @RequestBody UserProfileUpdateRequest request) {
        User user = userService.getUser(userId);
        userProfileService.updateProfile(user, request.name(), request.profileImageUrl(), request.goal());
    }
}

package com.kdt.wellmade.domain.mapage;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.kdt.wellmade.domain.user.User;
import com.kdt.wellmade.domain.user.UserService;

import jakarta.validation.Valid;
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
    public void updateMyProfile(@AuthenticationPrincipal Long userId,@Valid @RequestBody UserProfileUpdateRequest request) {
        User user = userService.getUser(userId);
        userProfileService.updateProfile(user, request.name(), request.profileImageUrl(), request.goal());
    }

    // 닉네임 수정(PUT /profile)과 분리해둠 - 그쪽은 name을 필수로 받는 전체 수정이라
    // 성별만 바꾸려고 닉네임까지 매번 실어보내야 하는 걸 피하기 위함
    @PutMapping("/body")
    public void updateMyBody(@AuthenticationPrincipal Long userId, @Valid @RequestBody UserProfileBodyRequest request) {
        User user = userService.getUser(userId);
        userProfileService.updateBody(user, request.gender(), request.heightCm(), request.birthYear());
    }
}

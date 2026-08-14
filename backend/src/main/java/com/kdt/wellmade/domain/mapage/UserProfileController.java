package com.kdt.wellmade.domain.mapage;

import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import lombok.RequiredArgsConstructor;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestParam;


@RestController
@RequestMapping("/api/users/me/profile")
@RequiredArgsConstructor
public class UserProfileController {
    private final UserProfileService userProfileService;

    @GetMapping
    public UserProfileResponse getMyProfile(@AuthenticationPrincipal ... user) {
        ...
    }

    @PutMapping
    public void updateMyProfile(@AuthenticationPrincipal ... user){
        
    }
    
}

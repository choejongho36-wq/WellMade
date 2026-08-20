package com.kdt.wellmade.domain.mapage;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.kdt.wellmade.domain.user.User;


import lombok.RequiredArgsConstructor;

@Service
@RequiredArgsConstructor
public class UserProfileService {
    
    private final UserProfileRepository userProfileRepository;

    @Transactional(readOnly = true)
    public UserProfile getProfile(User user) {
        return userProfileRepository.findByUser(user)
                .orElseThrow(() -> new IllegalArgumentException("프로필이 없습니다."));
    }

    @Transactional
    public void updateProfile(User user, String name, String profileImageUrl, Goal goal) {
        UserProfile profile = getProfile(user);
        profile.update(name, profileImageUrl, goal);
    }

   

}

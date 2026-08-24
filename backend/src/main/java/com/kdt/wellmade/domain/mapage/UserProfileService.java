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
        if (!name.equals(profile.getName()) && userProfileRepository.existsByName(name)) {
            throw new IllegalArgumentException("이미 사용 중인 닉네임입니다.");
        }
        profile.update(name, profileImageUrl, goal);
    }

   

}

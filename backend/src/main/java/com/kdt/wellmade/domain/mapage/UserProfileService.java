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

    /** 성별/키/출생연도 수정. null인 항목은 기존 값 유지 */
    @Transactional
    public void updateBody(User user, Gender gender, Double heightCm, Integer birthYear) {
        getProfile(user).updateBody(gender, heightCm, birthYear);
    }

    /** 목표 섭취량 직접 수정. 전부 null로 넘기면 추천값 자동계산으로 되돌림 */
    @Transactional
    public void updateTarget(User user, Double kcal, Double proteinG, Double carbsG, Double fatG) {
        getProfile(user).updateTarget(kcal, proteinG, carbsG, fatG);
    }
}

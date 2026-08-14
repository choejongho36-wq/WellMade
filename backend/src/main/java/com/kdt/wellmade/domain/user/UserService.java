package com.kdt.wellmade.domain.user;

import java.util.concurrent.ThreadLocalRandom;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.kdt.wellmade.domain.mapage.UserProfile;
import com.kdt.wellmade.domain.mapage.UserProfileRepository;

import lombok.RequiredArgsConstructor;

@Service
@RequiredArgsConstructor
public class UserService {
    private final UserRepository userRepository;
    private final UserProfileRepository userProfileRepository;

    private static final String[] ADJECTIVES = {
        "행복한", "용감한", "귀여운", "든든한", "씩씩한", "차분한", "활발한", "느긋한"
    };
    private static final String[] NOUNS = {
        "호랑이", "고양이", "펭귄", "여우", "다람쥐", "코끼리", "부엉이", "토끼"
    };

    @Transactional
    public User loginOrRegister(Provider provider, String providerId, String email){
        return userRepository.findByProviderAndProviderId(provider, providerId)
               .orElseGet(() -> {
                  User saved = userRepository.save(
                    User.builder()
                        .provider(provider)
                        .providerId(providerId)
                        .email(email)
                        .build());
                    userProfileRepository.save(
                        UserProfile.builder()
                            .user(saved)
                            .build());
                    return saved;
    });
    }

    @Transactional(readOnly = true)
    public User getUser(Long userId) {
        return userRepository.findById(userId)
                .orElseThrow(() -> new IllegalArgumentException("존재하지 않는 유저입니다."));
    }

    private String generateRandomNickname() {
        ThreadLocalRandom random = ThreadLocalRandom.current();
        String nickname;
        do {
             String adjective = ADJECTIVES[random.nextInt(ADJECTIVES.length)];
             String noun = NOUNS[random.nextInt(NOUNS.length)];
             int number = random.nextInt(1000, 10000);
             nickname =  adjective + noun + number;
        } while (userProfileRepository.exiexistsByName(nickname));
       return nickname;
    }
}

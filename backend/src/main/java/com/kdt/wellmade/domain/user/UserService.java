package com.kdt.wellmade.domain.user;

import java.util.concurrent.ThreadLocalRandom;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.kdt.wellmade.domain.chat.ChatMessageRepository;
import com.kdt.wellmade.domain.inbody.InbodyRecordRepository;
import com.kdt.wellmade.domain.mapage.UserProfile;
import com.kdt.wellmade.domain.mapage.UserProfileRepository;
import com.kdt.wellmade.domain.nutrition.MealLoggingService;
import com.kdt.wellmade.global.security.SocialUnlinkClient;

import lombok.RequiredArgsConstructor;

@Service
@RequiredArgsConstructor
public class UserService {
    private final UserRepository userRepository;
    private final UserProfileRepository userProfileRepository;
    private final ChatMessageRepository chatMessageRepository;
    private final InbodyRecordRepository inbodyRecordRepository;
    private final MealLoggingService mealLoggingService;
    private final SocialUnlinkClient socialUnlinkClient;

    private static final String[] ADJECTIVES = {
        "행복한", "용감한", "귀여운", "든든한", "씩씩한", "차분한", "활발한", "느긋한"
    };
    private static final String[] NOUNS = {
        "호랑이", "고양이", "펭귄", "여우", "다람쥐", "코끼리", "부엉이", "토끼"
    };

    @Transactional
    public User loginOrRegister(Provider provider, String providerId, String email, String socialAccessToken){
        User user = userRepository.findByProviderAndProviderId(provider, providerId)
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
                            .name(generateRandomNickname())
                            .build());
                    return saved;
    });
        user.updateSocialAccessToken(socialAccessToken); // 매 로그인마다 갱신 - 탈퇴 시 unlink에 사용
        return user;
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
        } while (userProfileRepository.existsByName(nickname));
       return nickname;
    }

    // diet_meals/chat_messages/inbody_records는 users FK가 CASCADE가 아니라 NO ACTION이라,
    // 먼저 안 지우고 users만 지우면 외래키 제약 위반으로 그대로 실패함
    @Transactional
    public void withdraw(Long userId) {
        User user = getUser(userId);
        socialUnlinkClient.unlink(user.getProvider(), user.getSocialAccessToken());
        mealLoggingService.deleteAllForUser(userId);
        chatMessageRepository.deleteByUser(user);
        inbodyRecordRepository.deleteByUser(user);
        userProfileRepository.deleteByUser(user);
        userRepository.delete(user);
    }
}

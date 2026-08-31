package com.kdt.wellmade.global.security;

import java.time.Duration;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

import com.kdt.wellmade.domain.user.Provider;

/**
 * 회원 탈퇴 시 소셜 제공자 쪽 연동도 끊는다.
 * 카카오/네이버는 로그인 검수 가이드가 연동 해제를 요구하고, 구글은 관행적으로 토큰을 revoke한다.
 *
 * 전부 best-effort - access token이 없거나 만료됐어도 예외를 삼키고 탈퇴 자체는 계속 진행한다.
 * (제대로 하려면 refresh token을 저장해 갱신 후 호출해야 하지만, 로그인 전용 앱이라 거기까진 안 함)
 */
@Component
public class SocialUnlinkClient {

    private static final Logger log = LoggerFactory.getLogger(SocialUnlinkClient.class);

    private final RestClient restClient;
    private final String naverClientId;
    private final String naverClientSecret;

    public SocialUnlinkClient(
            @Value("${spring.security.oauth2.client.registration.naver.client-id}") String naverClientId,
            @Value("${spring.security.oauth2.client.registration.naver.client-secret}") String naverClientSecret) {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(Duration.ofSeconds(3));
        factory.setReadTimeout(Duration.ofSeconds(3));
        this.restClient = RestClient.builder().requestFactory(factory).build();
        this.naverClientId = naverClientId;
        this.naverClientSecret = naverClientSecret;
    }

    public void unlink(Provider provider, String accessToken) {
        if (accessToken == null || accessToken.isBlank()) {
            log.warn("{} access token이 없어 연동 해제를 건너뜀", provider);
            return;
        }
        try {
            switch (provider) {
                case GOOGLE -> restClient.post()
                        .uri("https://oauth2.googleapis.com/revoke?token={t}", accessToken)
                        .retrieve().toBodilessEntity();
                case KAKAO -> restClient.post()
                        .uri("https://kapi.kakao.com/v1/user/unlink")
                        .header("Authorization", "Bearer " + accessToken)
                        .retrieve().toBodilessEntity();
                case NAVER -> restClient.post()
                        .uri("https://nid.naver.com/oauth2.0/token"
                                + "?grant_type=delete&client_id={id}&client_secret={secret}"
                                + "&access_token={t}&service_provider=NAVER",
                                naverClientId, naverClientSecret, accessToken)
                        .retrieve().toBodilessEntity();
            }
            log.info("{} 연동 해제 완료", provider);
        } catch (Exception e) {
            log.warn("{} 연동 해제 실패 (탈퇴는 계속 진행): {}", provider, e.getMessage());
        }
    }
}

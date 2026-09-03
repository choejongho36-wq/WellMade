package com.kdt.wellmade.global.config;

import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

/**
 * 또래 비교(국민건강통계) 조회용 AI 서버(FastAPI) RestClient.
 *
 * 지금까지 AI 서버는 프론트가 직접 불렀지만(frontend/src/lib/aiApi.js), 챗봇 도구는 서버에서
 * 돌아야 해서 백엔드에도 통로가 필요해졌다. AI 서버는 인증이 없고 계산만 하므로 토큰은 붙이지 않는다.
 *
 * Ollama와 달리 단순 조회라 타임아웃을 짧게 잡는다 - 또래 비교는 부가 정보라서, 늦게 오느니
 * 빨리 실패하고 "지금 확인할 수 없다"고 답하는 편이 낫다.
 */
@Configuration
public class AiServerClientConfig {

    @Bean
    public RestClient aiRestClient(@Value("${ai.base-url:http://localhost:8000}") String baseUrl) {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(Duration.ofSeconds(2));
        factory.setReadTimeout(Duration.ofSeconds(5));

        return RestClient.builder()
                .baseUrl(baseUrl)
                .requestFactory(factory)
                .build();
    }
}

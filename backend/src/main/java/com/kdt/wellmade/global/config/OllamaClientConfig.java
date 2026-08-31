package com.kdt.wellmade.global.config;

import java.time.Duration;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

/**
 * ChatService / FoodParsingService가 공유하는 Ollama용 RestClient.
 *
 * 기존에는 각 서비스가 `new RestTemplate()`을 직접 들고 있어서 타임아웃이 무제한이었음.
 * 로컬 Qwen이 응답을 안 주면 톰캣 워커 스레드가 계속 잡혀 있다가 서버 전체가 멎는 문제가 있어서,
 * connect/read 타임아웃을 명시적으로 건 빈 하나로 통일함.
 */
@Configuration
public class OllamaClientConfig {

    @Bean
    public RestClient ollamaRestClient(@Value("${ollama.base-url:http://localhost:11434}") String baseUrl) {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(Duration.ofSeconds(3));
        // 로컬 7B 기준 생성이 느릴 수 있어 read timeout은 넉넉하게, 그래도 무제한은 아니게
        factory.setReadTimeout(Duration.ofSeconds(60));

        return RestClient.builder()
                .baseUrl(baseUrl)
                .requestFactory(factory)
                .build();
    }

    /**
     * 챗봇 SSE 스트리밍용 워커. SSE 응답은 요청 스레드 밖에서 토큰을 흘려보내야 하고,
     * 그 스레드는 Ollama 응답을 기다리며 대부분 블로킹 I/O 상태라 가상 스레드가 잘 맞음.
     * ExecutorService 빈이라 컨텍스트 종료 시 스프링이 shutdown 해줌.
     */
    @Bean
    ExecutorService chatStreamExecutor() {
        return Executors.newVirtualThreadPerTaskExecutor();
    }
}

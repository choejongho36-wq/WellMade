package com.kdt.wellmade.global.config;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Spring Boot 4.1부터 자동 설정되는 ObjectMapper는 Jackson 3(tools.jackson.databind)이라,
 * 코드 곳곳(HolidayService, ChatService 등)이 생성자로 요구하는 구버전
 * com.fasterxml.jackson.databind.ObjectMapper는 더 이상 빈으로 등록되지 않는다.
 * jackson-databind 2.x 라이브러리 자체는 classpath에 있으므로(jjwt-jackson 등) 빈만 열어준다.
 */
@Configuration
public class JacksonConfig {

    @Bean
    public ObjectMapper objectMapper() {
        return new ObjectMapper();
    }
}

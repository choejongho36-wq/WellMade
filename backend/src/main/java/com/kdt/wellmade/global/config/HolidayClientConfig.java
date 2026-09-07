package com.kdt.wellmade.global.config;

import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

/**
 * 공공데이터포털(data.go.kr) 특일 정보 API 호출용 RestClient.
 *
 * 예전엔 HolidayService가 {@code new RestTemplate()}을 직접 들고 있어서 타임아웃이 무제한이었다.
 * OllamaClientConfig 주석에 적어둔 것과 같은 문제 - 상대가 안 주면 톰캣 워커 스레드가 계속
 * 잡혀 있는다. data.go.kr은 실제로 느리거나 점검 중인 날이 있으므로 짧게 끊는다.
 * 공휴일은 달력의 부가 정보라, 늦게 오느니 빨리 포기하고 평일로 그리는 편이 낫다.
 *
 * baseUrl을 두지 않는 이유: 서비스키가 이미 URL 인코딩된 문자열이라 절대 URI를 통째로 넘겨야 함
 * (HolidayService 참고).
 */
@Configuration
public class HolidayClientConfig {

    @Bean
    public RestClient holidayRestClient() {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(Duration.ofSeconds(2));
        factory.setReadTimeout(Duration.ofSeconds(5));

        return RestClient.builder().requestFactory(factory).build();
    }
}

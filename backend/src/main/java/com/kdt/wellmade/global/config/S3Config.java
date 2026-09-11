package com.kdt.wellmade.global.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;

/**
 * 신고(pose report) 원본 저장용 S3 클라이언트. AI 서버(ai/app/pose/dtw_template_store.py)가
 * boto3 기본 자격증명 체인을 쓰는 것과 같은 방식으로, 여기도 DefaultCredentialsProvider를
 * 써서(환경변수/프로파일/IAM 롤 중 하나) 액세스 키를 코드/설정 파일에 직접 넣지 않는다.
 */
@Configuration
public class S3Config {

    @Bean
    public S3Client s3Client(@Value("${app.s3.region}") String region) {
        return S3Client.builder()
                .region(Region.of(region))
                .credentialsProvider(DefaultCredentialsProvider.create())
                .build();
    }

    @Bean
    public S3Presigner s3Presigner(@Value("${app.s3.region}") String region) {
        return S3Presigner.builder()
                .region(Region.of(region))
                .credentialsProvider(DefaultCredentialsProvider.create())
                .build();
    }
}

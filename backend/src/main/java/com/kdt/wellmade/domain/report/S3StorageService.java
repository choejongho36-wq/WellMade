package com.kdt.wellmade.domain.report;

import java.io.IOException;
import java.time.Duration;
import java.util.UUID;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.DeleteObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;
import software.amazon.awssdk.services.s3.presigner.model.GetObjectPresignRequest;

/**
 * 신고된 사진/영상 원본을 S3에 올리고/받고/지우는 역할만 한다. 좌표 추출 등 무거운 연산은
 * 여기서 하지 않는다(서버는 저장만, 계산은 로컬 오프라인 스크립트 — 8/27 addendum 원칙).
 */
@Service
public class S3StorageService {

    private final S3Client s3Client;
    private final S3Presigner s3Presigner;
    private final String bucket;

    public S3StorageService(S3Client s3Client, S3Presigner s3Presigner,
                             @Value("${app.s3.reports-bucket}") String bucket) {
        this.s3Client = s3Client;
        this.s3Presigner = s3Presigner;
        this.bucket = bucket;
    }

    /** 신고 원본 업로드. key는 "pose-reports/{sourceType}/{yyyy}/{uuid}-{원본파일명}" 형태로 만든다. */
    public String upload(MultipartFile file, ReportSourceType sourceType) throws IOException {
        String safeName = file.getOriginalFilename() == null ? "upload" : file.getOriginalFilename().replaceAll("[^a-zA-Z0-9._-]", "_");
        String key = "pose-reports/%s/%d/%s-%s".formatted(
                sourceType.name().toLowerCase(), java.time.Year.now().getValue(), UUID.randomUUID(), safeName);

        s3Client.putObject(
                PutObjectRequest.builder()
                        .bucket(bucket)
                        .key(key)
                        .contentType(file.getContentType())
                        .build(),
                RequestBody.fromInputStream(file.getInputStream(), file.getSize()));
        return key;
    }

    public byte[] download(String key) {
        return s3Client.getObjectAsBytes(GetObjectRequest.builder().bucket(bucket).key(key).build()).asByteArray();
    }

    public void delete(String key) {
        s3Client.deleteObject(DeleteObjectRequest.builder().bucket(bucket).key(key).build());
    }

    /** 관리자 화면에서 신고 원본을 미리보기용으로 볼 수 있게 잠깐(10분)만 유효한 URL을 발급한다. */
    public String presignedGetUrl(String key) {
        var presignRequest = GetObjectPresignRequest.builder()
                .signatureDuration(Duration.ofMinutes(10))
                .getObjectRequest(GetObjectRequest.builder().bucket(bucket).key(key).build())
                .build();
        return s3Presigner.presignGetObject(presignRequest).url().toString();
    }
}

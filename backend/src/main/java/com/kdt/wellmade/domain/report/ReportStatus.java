package com.kdt.wellmade.domain.report;

public enum ReportStatus {
    PENDING,   // 관리자 검토 대기
    APPROVED,  // 액티브러닝 템플릿 후보로 승인 (오프라인 파이프라인 대상)
    REJECTED   // 반려 (S3 원본도 함께 삭제)
}

package com.kdt.wellmade.domain.report;

/** 신고 사유 카테고리. OTHER 선택 시에만 PoseReport.reasonDetail(자유 입력)을 함께 받는다. */
public enum ReportReasonCategory {
    FALSE_POSITIVE,      // 정상인데 이상하다고 판정함
    FALSE_NEGATIVE,      // 이상한데 정상으로 판정함
    POSE_DETECTION_ERROR,// 자세 인식(스켈레톤)이 잘못 잡힘
    OTHER                // 기타 (reasonDetail 필수)
}

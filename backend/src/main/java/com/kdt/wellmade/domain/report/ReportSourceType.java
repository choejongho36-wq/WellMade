package com.kdt.wellmade.domain.report;

/** 신고가 어느 화면에서 접수됐는지. 원본 미디어의 성격(정지 사진 vs 세션 시계열)이 달라 구분한다. */
public enum ReportSourceType {
    PHOTO,   // 사진측정(PhotoCoachingPage) 결과 신고
    SESSION  // 실시간 세션 리포트(SquatCoachingPage ReportView) 신고
}

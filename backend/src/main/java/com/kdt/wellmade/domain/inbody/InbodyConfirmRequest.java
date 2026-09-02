package com.kdt.wellmade.domain.inbody;

public record InbodyConfirmRequest(
    Double weightKg,
    Double skeletalMuscleMassKg,
    Double bodyFatPercentage,
    Integer basalMetabolicRateKcal,
    Double bmi,
    /**
     * true면 새 기록을 추가하는 대신 가장 최근 기록을 이 값으로 갈아끼운다.
     * 사진을 잘못 올렸을 때 바로잡는 용도 - 추이 그래프에 점이 늘어나면 안 되기 때문.
     * (생략하면 null = 새 기록 추가. 기존 클라이언트와 호환됨)
     */
    Boolean replaceLatest
) {
}

package com.kdt.wellmade.domain.inbody;

public record InbodyConfirmRequest(
    Double weightKg,
    Double skeletalMuscleMassKg,
    Double bodyFatPercentage,
    Integer basalMetabolicRateKcal,
    Double bmi
) {
}

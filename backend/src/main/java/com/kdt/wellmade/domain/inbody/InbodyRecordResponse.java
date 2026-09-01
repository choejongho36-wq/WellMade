package com.kdt.wellmade.domain.inbody;

import java.time.LocalDateTime;

public record InbodyRecordResponse(
    Long id,
    Double weightKg,
    Double skeletalMuscleMassKg,
    Double bodyFatPercentage,
    Integer basalMetabolicRateKcal,
    Double bmi,
    LocalDateTime measuredAt
) {
    public static InbodyRecordResponse from(InbodyRecord record) {
        return new InbodyRecordResponse(
            record.getId(),
            record.getWeightKg(),
            record.getSkeletalMuscleMassKg(),
            record.getBodyFatPercentage(),
            record.getBasalMetabolicRateKcal(),
            record.getBmi(),
            record.getCreatedAt()
        );
    }
}

package com.kdt.wellmade.domain.mapage;

import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;

/** 성별/키/출생연도 수정 요청. null인 항목은 기존 값을 유지함 */
public record UserProfileBodyRequest(
        Gender gender,
        @DecimalMin("100.0") @DecimalMax("250.0") Double heightCm,
        @Min(1900) @Max(2100) Integer birthYear) {
}

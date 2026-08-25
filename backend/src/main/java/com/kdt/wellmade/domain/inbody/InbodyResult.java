package com.kdt.wellmade.domain.inbody;

 
/**
 * 인바디 OCR 추출 결과.
 *
 * 필드가 null이면 해당 값을 못 읽었다는 뜻이므로, 챗봇에서 사용자에게
 * "OO 값을 못 읽었어요, 직접 입력해주세요"처럼 안내해야 함.
 *
 * rawText는 디버깅/로그용으로 남겨두되, 사용자에게 그대로 노출하지는 않는 걸 권장.
 */
public class InbodyResult {
 
    private final Double weightKg;
    private final Double skeletalMuscleMassKg;
    private final Double bodyFatPercentage;
    private final Integer basalMetabolicRateKcal;
    private final Double bmi;
    private final String rawText;

    public InbodyResult(Double weightKg, Double skeletalMuscleMassKg,
                                   Double bodyFatPercentage, Integer basalMetabolicRateKcal,
                                   Double bmi,
                                   String rawText) {
        this.weightKg = weightKg;
        this.skeletalMuscleMassKg = skeletalMuscleMassKg;
        this.bodyFatPercentage = bodyFatPercentage;
        this.basalMetabolicRateKcal = basalMetabolicRateKcal;
        this.bmi = bmi;
        this.rawText = rawText;
    }
 
    /** 필수 값(체중/골격근량/체지방률)이 전부 읽혔는지 - 이게 false면 재촬영 요청 등을 고려 */
    public boolean isComplete() {
        return weightKg != null && skeletalMuscleMassKg != null && bodyFatPercentage != null;
    }
 
    public Double getWeightKg() {
        return weightKg;
    }
 
    public Double getSkeletalMuscleMassKg() {
        return skeletalMuscleMassKg;
    }
 
    public Double getBodyFatPercentage() {
        return bodyFatPercentage;
    }
 
    public Integer getBasalMetabolicRateKcal() {
        return basalMetabolicRateKcal;
    }

    public Double getBmi() {
        return bmi;
    }

    public String getRawText() {
        return rawText;
    }
 
    @Override
    public String toString() {
        return "InbodyExtractionResult{" +
                "weightKg=" + weightKg +
                ", skeletalMuscleMassKg=" + skeletalMuscleMassKg +
                ", bodyFatPercentage=" + bodyFatPercentage +
                ", basalMetabolicRateKcal=" + basalMetabolicRateKcal +
                ", bmi=" + bmi +
                '}';
    }
}
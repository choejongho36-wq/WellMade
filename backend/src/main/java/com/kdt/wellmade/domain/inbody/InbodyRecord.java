package com.kdt.wellmade.domain.inbody;

import java.time.LocalDateTime;

import com.kdt.wellmade.domain.user.User;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;
import lombok.AccessLevel;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Entity
@Table(name = "inbody_records")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class InbodyRecord {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "user_id", nullable = false)
    private User user;

    @Column(name = "weight_kg")
    private Double weightKg;

    @Column(name = "skeletal_muscle_mass_kg")
    private Double skeletalMuscleMassKg;

    @Column(name = "body_fat_percentage")
    private Double bodyFatPercentage;

    @Column(name = "basal_metabolic_rate_kcal")
    private Integer basalMetabolicRateKcal;

    @Column(name = "bmi")
    private Double bmi;

    @Column(name = "created_at", nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @Builder
    public InbodyRecord(User user, Double weightKg, Double skeletalMuscleMassKg,
                         Double bodyFatPercentage, Integer basalMetabolicRateKcal,
                         Double bmi) {
        this.user = user;
        this.weightKg = weightKg;
        this.skeletalMuscleMassKg = skeletalMuscleMassKg;
        this.bodyFatPercentage = bodyFatPercentage;
        this.basalMetabolicRateKcal = basalMetabolicRateKcal;
        this.bmi = bmi;
    }

    @PrePersist
    protected void onCreate() {
        this.createdAt = LocalDateTime.now();
    }
}

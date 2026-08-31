package com.kdt.wellmade.domain.mapage;

import java.time.LocalDateTime;

import com.kdt.wellmade.domain.user.User;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.OneToOne;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import lombok.AccessLevel;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Entity
@Table(name = "user_profiles")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class UserProfile {
    
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "user_id", nullable = false, unique = true)
    private User user;

    @Column(length = 50, unique = true)
    private String name;

    @Column(name = "profile_image_url", length = 500)
    private String profileImageUrl;

    @Enumerated(EnumType.STRING)
    @Column(length = 20)
    private Goal goal;                  // LOSE, GAIN, MAINTAIN

    // 기초대사량(Mifflin-St Jeor) 계산에 필요한 신체 정보. 셋 다 있어야 성별/키 반영 추정이 가능하고,
    // 하나라도 비면 체중 기반 대략 추정으로 떨어짐.
    @Enumerated(EnumType.STRING)
    @Column(length = 10)
    private Gender gender;              // MALE, FEMALE

    @Column(name = "height_cm")
    private Double heightCm;

    @Column(name = "birth_year")
    private Integer birthYear;

    // 전부 null이면 목표+인바디로 자동 계산한 추천값을 씀. 사용자가 직접 수정하면 4개 다 채워서 저장함.
    @Column(name = "target_kcal")
    private Double targetKcal;

    @Column(name = "target_protein_g")
    private Double targetProteinG;

    @Column(name = "target_carbs_g")
    private Double targetCarbsG;

    @Column(name = "target_fat_g")
    private Double targetFatG;

    @Column(name = "created_at", nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @Column(name = "updated_at", nullable = false)
    private LocalDateTime updatedAt;

    @Builder
    public UserProfile(User user, String name, String profileImageUrl, Goal goal) {
        this.user = user;
        this.name = name;
        this.profileImageUrl = profileImageUrl;
        this.goal = goal;
    }

    @PrePersist
    protected void onCreate() {
        this.createdAt = LocalDateTime.now();
        this.updatedAt = LocalDateTime.now();
    }

    @PreUpdate
    protected void onUpdate() {
        this.updatedAt = LocalDateTime.now();
    }

    public void update(String name, String profileImageUrl, Goal goal) {
        this.name = name;
        this.profileImageUrl = profileImageUrl;
        if (goal != null) {
            this.goal = goal;
        }
    }

    /** 성별/키/출생연도 수정. null인 항목은 기존 값을 유지함 */
    public void updateBody(Gender gender, Double heightCm, Integer birthYear) {
        if (gender != null) {
            this.gender = gender;
        }
        if (heightCm != null) {
            this.heightCm = heightCm;
        }
        if (birthYear != null) {
            this.birthYear = birthYear;
        }
    }

    /** 목표 섭취량 직접 수정. 전부 null로 넘기면 추천값 자동계산으로 되돌림 */
    public void updateTarget(Double kcal, Double proteinG, Double carbsG, Double fatG) {
        this.targetKcal = kcal;
        this.targetProteinG = proteinG;
        this.targetCarbsG = carbsG;
        this.targetFatG = fatG;
    }
}

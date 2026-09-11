package com.kdt.wellmade.domain.workout;

import java.time.LocalDateTime;
import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;

import com.kdt.wellmade.domain.report.ReportSourceType;

public interface WorkoutSessionLogRepository extends JpaRepository<WorkoutSessionLog, Long> {

    long countByCreatedAtAfter(LocalDateTime dateTime);

    long countBySourceTypeAndCreatedAtAfter(ReportSourceType sourceType, LocalDateTime dateTime);

    long countByResultNormalAndCreatedAtAfter(boolean resultNormal, LocalDateTime dateTime);

    // 이슈 부위 빈도 집계(issueCounts JSON 파싱)와 관리자 대시보드 "최근 활동" 목록용
    List<WorkoutSessionLog> findByCreatedAtAfterOrderByCreatedAtDesc(LocalDateTime dateTime);

    List<WorkoutSessionLog> findTop5ByOrderByCreatedAtDesc();
}

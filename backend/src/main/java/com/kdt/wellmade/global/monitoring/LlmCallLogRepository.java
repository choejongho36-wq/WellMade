package com.kdt.wellmade.global.monitoring;

import java.time.LocalDateTime;
import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import com.kdt.wellmade.global.monitoring.LlmCallLog.Feature;

public interface LlmCallLogRepository extends JpaRepository<LlmCallLog, Long> {

    long countByFeatureAndCreatedAtAfter(Feature feature, LocalDateTime dateTime);

    long countByFeatureAndSuccessFalseAndCreatedAtAfter(Feature feature, LocalDateTime dateTime);

    @Query("SELECT AVG(l.latencyMs) FROM LlmCallLog l "
            + "WHERE l.feature = :feature AND l.success = true AND l.createdAt >= :dateTime")
    Double averageLatencyMs(@Param("feature") Feature feature, @Param("dateTime") LocalDateTime dateTime);

    // 오늘 어떤 도구가 얼마나 호출됐는지는 부위 종류가 적어 DB 집계 대신 자바에서 센다
    List<LlmCallLog> findByFeatureAndCreatedAtAfter(Feature feature, LocalDateTime dateTime);
}

package com.kdt.wellmade.domain.report;

import java.util.List;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PoseReportRepository extends JpaRepository<PoseReport, Long> {
    Page<PoseReport> findByStatusOrderByCreatedAtDesc(ReportStatus status, Pageable pageable);
    Page<PoseReport> findAllByOrderByCreatedAtDesc(Pageable pageable);
    long countByStatus(ReportStatus status);
    List<PoseReport> findByStatusOrderByCreatedAtAsc(ReportStatus status);
}

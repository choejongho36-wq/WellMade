package com.kdt.wellmade.domain.support;

import java.util.List;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface InquiryRepository extends JpaRepository<Inquiry, Long> {

    // 문의 게시판 목록(전체 회원 공개, 제목만 - 비밀글은 서비스 계층에서 본문을 가림)
    List<Inquiry> findAllByOrderByCreatedAtDesc();

    // 관리자 목록 - 상태별 필터 + 페이징
    Page<Inquiry> findByStatusOrderByCreatedAtDesc(InquiryStatus status, Pageable pageable);
    Page<Inquiry> findAllByOrderByCreatedAtDesc(Pageable pageable);
}

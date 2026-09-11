package com.kdt.wellmade.domain.support;

import java.util.List;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface NoticeRepository extends JpaRepository<Notice, Long> {
    List<Notice> findAllByOrderByPinnedDescCreatedAtDescIdDesc();
    Page<Notice> findAllByOrderByPinnedDescCreatedAtDescIdDesc(Pageable pageable);
}

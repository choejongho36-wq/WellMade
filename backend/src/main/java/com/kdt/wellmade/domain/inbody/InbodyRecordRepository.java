package com.kdt.wellmade.domain.inbody;

import java.util.List;
import java.util.Optional;

import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

import com.kdt.wellmade.domain.user.User;

public interface InbodyRecordRepository extends JpaRepository<InbodyRecord, Long> {
    Optional<InbodyRecord> findTopByUserOrderByCreatedAtDesc(User user);

    // 챗봇 툴콜링(get_inbody_history)에서 최근 N건 추세를 보여주기 위해 씀
    List<InbodyRecord> findByUserOrderByCreatedAtDesc(User user, Pageable pageable);

    void deleteByUser(User user);
}

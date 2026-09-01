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

    // 마이페이지 추이 그래프 — 오래된 순으로 전체
    List<InbodyRecord> findByUserOrderByCreatedAtAsc(User user);

    void deleteByUser(User user);

    // 남의 기록 id를 넣어도 0건이 지워지도록 user 조건을 같이 건다
    long deleteByIdAndUser(Long id, User user);
}

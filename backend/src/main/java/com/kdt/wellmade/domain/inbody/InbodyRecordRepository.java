package com.kdt.wellmade.domain.inbody;

import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

import com.kdt.wellmade.domain.user.User;

public interface InbodyRecordRepository extends JpaRepository<InbodyRecord, Long> {
    Optional<InbodyRecord> findTopByUserOrderByCreatedAtDesc(User user);
}

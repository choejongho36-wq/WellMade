package com.kdt.wellmade.domain.user;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.transaction.annotation.Transactional;

public interface UserRepository extends JpaRepository<User, Long> {

    Optional<User> findByProviderAndProviderId(Provider provider, String providerId);
    boolean existsByProviderAndProviderId(Provider provider, String providerId);

    // 관리자 대시보드 "오늘 신규가입" 카드용
    long countByCreatedAtAfter(LocalDateTime dateTime);

    // 관리자 대시보드 "오늘 활성 사용자(DAU)" 카드용 — lastActiveAt 기준
    long countByLastActiveAtAfter(LocalDateTime dateTime);

    // 관리자 대시보드 "최근 가입자" 목록용
    List<User> findTop5ByOrderByCreatedAtDesc();

    /**
     * 인증된 요청마다 부르지만 실제 UPDATE는 오늘 처음 활동한 사용자에게만 나간다(WHERE 절이
     * 오늘 안에 이미 갱신됐으면 걸러냄) — 매 요청마다 매번 쓰기가 나가는 걸 막기 위함.
     * @Modifying 쿼리라 필터(트랜잭션 밖)에서 바로 불러도 되도록 이 메서드 자체에
     * @Transactional을 붙였다.
     */
    @Transactional
    @Modifying
    @Query("UPDATE User u SET u.lastActiveAt = :now WHERE u.id = :userId "
            + "AND (u.lastActiveAt IS NULL OR u.lastActiveAt < :todayStart)")
    void touchLastActiveIfStale(
            @Param("userId") Long userId, @Param("todayStart") LocalDateTime todayStart, @Param("now") LocalDateTime now);
}

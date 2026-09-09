package com.kdt.wellmade.domain.user;

import java.time.LocalDateTime;
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface UserRepository extends JpaRepository<User, Long> {

    Optional<User> findByProviderAndProviderId(Provider provider, String providerId);
    boolean existsByProviderAndProviderId(Provider provider, String providerId);

    // 관리자 대시보드 "오늘 신규가입" 카드용
    long countByCreatedAtAfter(LocalDateTime dateTime);
}

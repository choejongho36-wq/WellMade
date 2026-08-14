package com.kdt.wellmade.domain.mapage;

import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

import com.kdt.wellmade.domain.user.User;

public interface UserProfileRepository extends JpaRepository<UserProfile, Long> {
    Optional<UserProfile> findByUser(User user);
    boolean existsByName(String name);
}

package com.kdt.wellmade.domain.nutrition;

import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.util.Optional;

/**
 * "밥"처럼 애매한 표현이 LIKE 폴백(FUZZY)으로만 매칭될 때, 사용자가 후보 중 하나를 직접 골라주면
 * 그 선택을 (user_id, 검색어) 단위로 저장해두는 서비스. 다음에 같은 검색어가 나오면 이 표를 먼저
 * 확인해서 후보 제시 없이 바로 정확매칭으로 처리함 - SLANG_ALIASES처럼 코드에 하드코딩하는 대신
 * 사용자 선택이 사전을 채워가는 구조.
 *
 * diet_meals와 마찬가지로 JPA 엔티티가 아니라 raw SQL로 관리함 (이 도메인의 기존 방식과 통일).
 * 테이블이 마이그레이션 파일 없이 관리되므로, 로컬 DB에 아래 DDL을 직접 실행해야 함:
 *
 *   CREATE TABLE user_food_alias (
 *       id BIGINT AUTO_INCREMENT PRIMARY KEY,
 *       user_id BIGINT NOT NULL,
 *       search_term VARCHAR(255) NOT NULL,
 *       resolved_food_name VARCHAR(255) NOT NULL,
 *       created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 *       UNIQUE KEY uq_user_food_alias (user_id, search_term)
 *   );
 */
@Service
public class UserFoodAliasService {

    private final JdbcTemplate jdbcTemplate;

    public UserFoodAliasService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    /** 이 사용자가 이 검색어에 대해 예전에 직접 골라둔 정확한 food_name이 있으면 반환 */
    public Optional<String> findResolved(Long userId, String searchTerm) {
        try {
            String resolved = jdbcTemplate.queryForObject(
                    "SELECT resolved_food_name FROM user_food_alias WHERE user_id = ? AND search_term = ?",
                    String.class, userId, searchTerm);
            return Optional.ofNullable(resolved);
        } catch (EmptyResultDataAccessException e) {
            return Optional.empty();
        }
    }

    /** 사용자가 후보 중 하나를 골랐을 때 저장 (같은 검색어로 다시 고르면 최신 선택으로 덮어씀) */
    public void save(Long userId, String searchTerm, String resolvedFoodName) {
        jdbcTemplate.update("""
                INSERT INTO user_food_alias (user_id, search_term, resolved_food_name)
                VALUES (?, ?, ?)
                ON DUPLICATE KEY UPDATE resolved_food_name = VALUES(resolved_food_name)
                """, userId, searchTerm, resolvedFoodName);
    }
}

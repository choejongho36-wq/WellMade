package com.kdt.wellmade.domain.chat;

import java.util.List;

import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

import com.kdt.wellmade.domain.user.User;

public interface ChatMessageRepository extends JpaRepository<ChatMessageEntity, Long> {

    // 최신순으로 N건 가져옴. 컨텍스트 구성이든 프론트 이력 표시든 "최근 N건을 시간순으로" 필요하므로
    // 호출부에서 이 결과를 시간순으로 뒤집어서 씀 (ASC 정렬 + limit은 "오래된 N건"이 되어버려 원하는 게 아님)
    List<ChatMessageEntity> findByUserOrderByCreatedAtDesc(User user, Pageable pageable);

    void deleteByUser(User user);
}

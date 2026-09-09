package com.kdt.wellmade.domain.support;

import java.time.LocalDateTime;

public record NoticeResponse(
        Long id, String title, String content, boolean pinned, LocalDateTime createdAt, LocalDateTime updatedAt) {
    public static NoticeResponse of(Notice notice) {
        return new NoticeResponse(
                notice.getId(), notice.getTitle(), notice.getContent(), notice.isPinned(),
                notice.getCreatedAt(), notice.getUpdatedAt());
    }
}

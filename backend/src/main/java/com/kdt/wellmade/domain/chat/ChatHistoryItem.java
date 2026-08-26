package com.kdt.wellmade.domain.chat;

import java.time.LocalDateTime;

public record ChatHistoryItem(String role, String content, LocalDateTime createdAt) {
}

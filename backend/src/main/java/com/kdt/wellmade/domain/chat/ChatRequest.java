package com.kdt.wellmade.domain.chat;

import java.util.List;

public record ChatRequest(List<ChatMessage> messages) {
}

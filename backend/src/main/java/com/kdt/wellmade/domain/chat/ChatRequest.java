package com.kdt.wellmade.domain.chat;

// 대화 이력을 서버(DB)가 갖게 되면서, 클라이언트는 매번 전체 배열이 아니라 새로 보낸 메시지 하나만 보내면 됨
public record ChatRequest(String message) {
}

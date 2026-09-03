package com.kdt.wellmade.domain.chat;

/**
 * 스트리밍이 아닌 챗봇 답변(메뉴 버튼 / 영양 분석)의 응답.
 *
 * action 은 답변 아래에 버튼을 그리라는 신호다(null 이면 버튼 없음) -
 * 값은 {@link ChatService#ACTION_REGISTER_INBODY} 같은 상수.
 */
public record ChatResponse(String content, String action) {

    public static ChatResponse of(String content) {
        return new ChatResponse(content, null);
    }
}

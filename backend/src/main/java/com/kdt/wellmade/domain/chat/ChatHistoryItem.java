package com.kdt.wellmade.domain.chat;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

/**
 * 화면에 다시 그릴 대화 한 줄.
 *
 * action/links는 답변에 딸려 나갔던 버튼과 바깥 링크다(운동 영상 등). 예전엔 SSE로만 보내서
 * 새로고침하면 사라졌는데, 이제 chat_messages.meta에 저장해두고 여기로 같이 내려준다.
 */
public record ChatHistoryItem(
        String role,
        String content,
        LocalDateTime createdAt,
        String action,
        List<Map<String, String>> links
) {
}

package com.kdt.wellmade.domain.chat;

import java.util.List;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.kdt.wellmade.domain.user.User;
import com.kdt.wellmade.domain.user.UserService;

import lombok.RequiredArgsConstructor;

/**
 * 챗봇 API. 대화 이력은 서버(DB)가 갖고 있으므로 /chat 요청엔 새 사용자 메시지 하나만 실어 보내면 됨.
 * /chat/history로 지금까지의 이력을 가져와 새로고침/재접속 후에도 대화를 이어볼 수 있음.
 */
@RestController
@RequestMapping("/api/users/me/chat")
@RequiredArgsConstructor
public class ChatController {

    private final ChatService chatService;
    private final UserService userService;

    @PostMapping
    public ChatResponse chat(@AuthenticationPrincipal Long userId, @RequestBody ChatRequest request) {
        User user = userService.getUser(userId);
        String reply = chatService.reply(user, request.message());
        return new ChatResponse(reply);
    }

    @GetMapping("/history")
    public List<ChatHistoryItem> history(@AuthenticationPrincipal Long userId) {
        User user = userService.getUser(userId);
        return chatService.getHistory(user);
    }

    @PostMapping("/nutrient-advice")
    public ChatResponse nutrientAdvice(@AuthenticationPrincipal Long userId) {
        User user = userService.getUser(userId);
        String reply = chatService.nutrientAdvice(user, userId);
        return new ChatResponse(reply);
    }
}

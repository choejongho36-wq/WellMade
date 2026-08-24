package com.kdt.wellmade.domain.chat;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.kdt.wellmade.domain.user.User;
import com.kdt.wellmade.domain.user.UserService;

import lombok.RequiredArgsConstructor;

@RestController
@RequestMapping("/api/users/me/chat")
@RequiredArgsConstructor
public class ChatController {

    private final ChatService chatService;
    private final UserService userService;

    @PostMapping
    public ChatResponse chat(@AuthenticationPrincipal Long userId, @RequestBody ChatRequest request) {
        User user = userService.getUser(userId);
        String reply = chatService.reply(user, request.messages());
        return new ChatResponse(reply);
    }
}

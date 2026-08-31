package com.kdt.wellmade.domain.chat;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.MediaType;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.kdt.wellmade.domain.user.User;
import com.kdt.wellmade.domain.user.UserService;
import com.kdt.wellmade.global.exception.ExternalServiceException;

import lombok.RequiredArgsConstructor;

/**
 * 챗봇 API. 대화 이력은 서버(DB)가 갖고 있으므로 /chat 요청엔 새 사용자 메시지 하나만 실어 보내면 됨.
 * /chat/history로 지금까지의 이력을 가져와 새로고침/재접속 후에도 대화를 이어볼 수 있음.
 *
 * /chat 은 답변을 토큰 단위로 흘려보내는 SSE 스트림임. 각 이벤트 data는 {"t":"조각"} JSON,
 * 오류 시 {"error":"..."} 한 건을 보낸 뒤 스트림을 닫음.
 */
@RestController
@RequestMapping("/api/users/me/chat")
@RequiredArgsConstructor
public class ChatController {

    private static final Logger log = LoggerFactory.getLogger(ChatController.class);
    private static final long STREAM_TIMEOUT_MS = 120_000L;

    // 이 프로젝트는 starter-web을 안 써서 ObjectMapper 자동 빈이 없음(ChatService도 직접 생성해 씀)
    private final ObjectMapper objectMapper = new ObjectMapper();

    private final ChatService chatService;
    private final UserService userService;
    private final ExecutorService chatStreamExecutor;

    @PostMapping(produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter chat(@AuthenticationPrincipal Long userId, @RequestBody ChatRequest request) {
        User user = userService.getUser(userId);
        SseEmitter emitter = new SseEmitter(STREAM_TIMEOUT_MS);

        chatStreamExecutor.execute(() -> {
            try {
                chatService.replyStream(user, request.message(), delta -> sendJson(emitter, Map.of("t", delta)));
            } catch (ExternalServiceException e) {
                // 원인은 ChatService 에서 이미 적절한 레벨로 로깅함. 안내 문구만 그대로 전달
                sendJsonQuietly(emitter, Map.of("error", e.getMessage()));
            } catch (Exception e) {
                log.warn("챗봇 스트리밍 실패 userId={}", userId, e);
                sendJsonQuietly(emitter, Map.of("error", "답변을 받지 못했어요. 잠시 후 다시 시도해 주세요."));
            }
            emitter.complete();
        });

        return emitter;
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

    private void sendJson(SseEmitter emitter, Map<String, String> payload) {
        try {
            emitter.send(SseEmitter.event().data(objectMapper.writeValueAsString(payload)));
        } catch (IOException e) {
            // 클라이언트가 끊었으면 스트리밍 스레드를 여기서 멈춰야 함
            throw new UncheckedIOException(e);
        }
    }

    private void sendJsonQuietly(SseEmitter emitter, Map<String, String> payload) {
        try {
            emitter.send(SseEmitter.event().data(objectMapper.writeValueAsString(payload)));
        } catch (IOException ignored) {
            // 이미 끊긴 스트림이면 무시
        }
    }
}

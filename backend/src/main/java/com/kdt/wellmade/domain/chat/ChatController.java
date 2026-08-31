package com.kdt.wellmade.domain.chat;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.MediaType;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.DeleteMapping;
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

    /**
     * 답변을 만들고 있는 사용자 목록. 프론트에는 전송 중 버튼을 막는 가드가 있지만 API를 직접
     * 호출하면 소용없고, 요청 하나가 GPU를 한동안 붙잡으므로 서버에서도 사용자당 1건으로 막는다.
     * (분산 배포로 가면 이 방식으로는 부족하니 그때는 공유 저장소 기반으로 옮겨야 함)
     */
    private final Set<Long> generating = ConcurrentHashMap.newKeySet();

    private final ChatService chatService;
    private final UserService userService;
    private final ExecutorService chatStreamExecutor;

    @PostMapping(produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter chat(@AuthenticationPrincipal Long userId, @RequestBody ChatRequest request) {
        User user = userService.getUser(userId);
        SseEmitter emitter = new SseEmitter(STREAM_TIMEOUT_MS);

        if (!generating.add(userId)) {
            sendJsonQuietly(emitter, Map.of("error", "아직 이전 질문에 답하고 있어요. 잠시만 기다려 주세요."));
            emitter.complete();
            return emitter;
        }

        chatStreamExecutor.execute(() -> {
            try {
                chatService.replyStream(user, request.message(), delta -> sendJson(emitter, Map.of("t", delta)));
            } catch (ExternalServiceException e) {
                // 원인은 ChatService 에서 이미 적절한 레벨로 로깅함. 안내 문구만 그대로 전달
                sendJsonQuietly(emitter, Map.of("error", e.getMessage()));
            } catch (Exception e) {
                log.warn("챗봇 스트리밍 실패 userId={}", userId, e);
                sendJsonQuietly(emitter, Map.of("error", "답변을 받지 못했어요. 잠시 후 다시 시도해 주세요."));
            } finally {
                generating.remove(userId);
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

    /** 대화 이력 전체 삭제 (본인 것만) */
    @DeleteMapping("/history")
    public void clearHistory(@AuthenticationPrincipal Long userId) {
        chatService.clearHistory(userService.getUser(userId));
    }

    @PostMapping("/nutrient-advice")
    public ChatResponse nutrientAdvice(@AuthenticationPrincipal Long userId) {
        // 이 경로도 같은 모델을 쓰므로 채팅과 같은 가드를 건다
        if (!generating.add(userId)) {
            return new ChatResponse("아직 이전 질문에 답하고 있어요. 잠시만 기다려 주세요.");
        }
        try {
            User user = userService.getUser(userId);
            return new ChatResponse(chatService.nutrientAdvice(user, userId));
        } finally {
            generating.remove(userId);
        }
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

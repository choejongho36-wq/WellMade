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
import org.springframework.web.bind.annotation.PathVariable;
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

    /**
     * 답변을 만들고 있는 사용자 목록. 프론트에는 전송 중 버튼을 막는 가드가 있지만 API를 직접
     * 호출하면 소용없고, 요청 하나가 GPU를 한동안 붙잡으므로 서버에서도 사용자당 1건으로 막는다.
     * (분산 배포로 가면 이 방식으로는 부족하니 그때는 공유 저장소 기반으로 옮겨야 함)
     */
    private final Set<Long> generating = ConcurrentHashMap.newKeySet();

    private final ChatService chatService;
    private final UserService userService;
    private final ExecutorService chatStreamExecutor;
    // starter-websocket이 starter-web을 끌고 오므로 스프링이 구성한 ObjectMapper 빈이 있다
    private final ObjectMapper objectMapper;

    @PostMapping(produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter chat(@AuthenticationPrincipal Long userId, @RequestBody ChatRequest request) {
        User user = userService.getUser(userId);
        // 검증은 워커에 넘기기 전에. executor 안에서 던지면 아래 catch (Exception)에 걸려
        // "답변을 받지 못했어요"로 뭉개진다 - 여기서 던져야 GlobalExceptionHandler가 400으로 답한다.
        String message = chatService.validateAndTrim(request.message());

        SseEmitter emitter = new SseEmitter(STREAM_TIMEOUT_MS);
        // 진단용. 타임아웃/전송 실패 자체는 스프링이 조용히 처리하고 generating은 finally로 풀리지만,
        // 어떤 이유로 스트림이 끝났는지가 로그에 안 남으면 나중에 확인할 방법이 없다.
        emitter.onTimeout(() -> log.warn("챗봇 SSE 타임아웃 userId={} ({}ms)", userId, STREAM_TIMEOUT_MS));
        emitter.onError(e -> log.warn("챗봇 SSE 오류 userId={}: {}", userId, e.toString()));

        if (!generating.add(userId)) {
            sendJsonQuietly(emitter, Map.of("error", "아직 이전 질문에 답하고 있어요. 잠시만 기다려 주세요."));
            emitter.complete();
            return emitter;
        }

        chatStreamExecutor.execute(() -> {
            try {
                String action = chatService.replyStream(user, message, request.followUpId(),
                        new ChatService.ReplyStream() {
                            @Override
                            public void delta(String text) {
                                sendJson(emitter, Map.of("t", text));
                            }

                            @Override
                            public void reset() {
                                // 도구를 부른 턴에서 최종 답변을 다시 스트리밍하기 직전 - 앞에 흘러간
                                // 조각(예고 문장 등)을 지우고 다시 그리라는 신호
                                sendJson(emitter, Map.of("reset", true));
                            }
                        });
                // 답변 뒤에 한 번만 - 프론트가 말풍선 아래에 버튼을 그린다 (예: 인바디 등록하러 가기)
                if (action != null) {
                    sendJsonQuietly(emitter, Map.of("action", action));
                }
            } catch (UncheckedIOException e) {
                // 사용자가 답변 도중 창을 닫았을 때(sendJson 실패). 보낼 곳이 없으니 안내도 못 하고,
                // 여기까지 만든 답변은 ChatService가 이미 저장했다.
                log.info("챗봇 스트리밍 중 클라이언트 연결이 끊김 userId={}", userId);
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

    /**
     * 메뉴 버튼 답변. 어떤 데이터를 볼지는 사용자가 이미 골랐으므로 모델에게 도구를 고르게 하지 않고
     * 서버가 직접 조회한다(ChatService.menuReply). 기록이 없으면 LLM을 아예 안 부르므로 즉시 응답한다.
     */
    @PostMapping("/menu/{menuId}")
    public ChatResponse menu(@AuthenticationPrincipal Long userId, @PathVariable String menuId) {
        // 이 경로도 같은 모델을 쓰므로 채팅과 같은 가드를 건다
        if (!generating.add(userId)) {
            return ChatResponse.of("아직 이전 질문에 답하고 있어요. 잠시만 기다려 주세요.");
        }
        try {
            User user = userService.getUser(userId);
            return chatService.menuReply(user, userId, menuId);
        } finally {
            generating.remove(userId);
        }
    }

    @PostMapping("/nutrient-advice")
    public ChatResponse nutrientAdvice(@AuthenticationPrincipal Long userId) {
        // 이 경로도 같은 모델을 쓰므로 채팅과 같은 가드를 건다
        if (!generating.add(userId)) {
            return ChatResponse.of("아직 이전 질문에 답하고 있어요. 잠시만 기다려 주세요.");
        }
        try {
            User user = userService.getUser(userId);
            return chatService.nutrientAdvice(user, userId);
        } finally {
            generating.remove(userId);
        }
    }

    private void sendJson(SseEmitter emitter, Map<String, ?> payload) {
        try {
            emitter.send(SseEmitter.event().data(objectMapper.writeValueAsString(payload)));
        } catch (IOException e) {
            // 클라이언트가 끊었으면 스트리밍 스레드를 여기서 멈춰야 함
            throw new UncheckedIOException(e);
        }
    }

    private void sendJsonQuietly(SseEmitter emitter, Map<String, ?> payload) {
        try {
            emitter.send(SseEmitter.event().data(objectMapper.writeValueAsString(payload)));
        } catch (IOException ignored) {
            // 이미 끊긴 스트림이면 무시
        }
    }
}

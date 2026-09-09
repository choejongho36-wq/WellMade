package com.kdt.wellmade.global.monitoring;

import java.time.LocalDateTime;

import com.kdt.wellmade.global.time.AppTime;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;
import lombok.AccessLevel;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

/**
 * 챗봇이 로컬 Ollama를 부르는 지점(HttpOllamaClient)과 도구를 실행하는 지점(ChatToolExecutor)에서
 * 한 건씩 남기는 호출 로그. 관리자 대시보드의 "AI 호출/폴백/에러율" 집계용이며, 실패해도 실제
 * 챗봇 응답 흐름을 막으면 안 되므로 기록 쪽에서 예외를 전부 삼킨다(호출부 참고).
 *
 * WellMade의 챗봇은 AWS Bedrock이 아니라 자체 호스팅한 Ollama 모델을 쓴다(OllamaClient 참고) —
 * "폴백"은 Ollama 호출이 실패했을 때 고정 안내 문구로 대신 응답하는 것을 뜻한다.
 */
@Entity
@Table(name = "llm_call_logs")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class LlmCallLog {

    public enum Feature {
        CHAT_REPLY,     // HttpOllamaClient.chatCompletion / chatCompletionStream
        CHAT_TOOL_CALL  // ChatToolExecutor.execute
    }

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private Feature feature;

    // CHAT_TOOL_CALL에서만 채워짐(어떤 도구인지)
    @Column(name = "tool_name", length = 50)
    private String toolName;

    @Column(nullable = false)
    private boolean success;

    // CHAT_REPLY에서만 채워짐(Ollama 응답까지 걸린 시간, ms)
    @Column(name = "latency_ms")
    private Long latencyMs;

    @Column(name = "created_at", nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @Builder
    public LlmCallLog(Feature feature, String toolName, boolean success, Long latencyMs) {
        this.feature = feature;
        this.toolName = toolName;
        this.success = success;
        this.latencyMs = latencyMs;
    }

    public static LlmCallLog chatReply(boolean success, long latencyMs) {
        return LlmCallLog.builder().feature(Feature.CHAT_REPLY).success(success).latencyMs(latencyMs).build();
    }

    public static LlmCallLog toolCall(String toolName, boolean success) {
        return LlmCallLog.builder().feature(Feature.CHAT_TOOL_CALL).toolName(toolName).success(success).build();
    }

    @PrePersist
    protected void onCreate() {
        this.createdAt = AppTime.now();
    }
}

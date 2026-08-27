package com.kdt.wellmade.global.exception;

/**
 * Ollama 등 외부 서비스 호출/응답 처리가 실패했을 때 던지는 예외.
 *
 * 메시지는 그대로 사용자에게 노출되는 것을 전제로 하므로, 원인(스택트레이스, 모델 원문 등)은
 * 이 예외를 던지는 지점에서 로그로 남기고, 여기엔 사용자向 안내 문구만 담을 것.
 */
public class ExternalServiceException extends RuntimeException {

    public ExternalServiceException(String userFacingMessage) {
        super(userFacingMessage);
    }

    public ExternalServiceException(String userFacingMessage, Throwable cause) {
        super(userFacingMessage, cause);
    }
}

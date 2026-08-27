package com.kdt.wellmade.global.exception;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<String> handleIllegalArgument(IllegalArgumentException e) {
        // 사용자 입력 검증 실패 - 메시지 자체가 사용자向 안내 문구이므로 그대로 내려도 안전함
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(e.getMessage());
    }

    @ExceptionHandler(ExternalServiceException.class)
    public ResponseEntity<String> handleExternalService(ExternalServiceException e) {
        // 마찬가지로 사용자向 안내 문구만 담겨 있음. 원인(스택트레이스, 모델 원문 등)은
        // 이 예외를 던진 지점에서 이미 로그로 남겼음
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body(e.getMessage());
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<String> handleUnexpected(Exception e) {
        // 이전엔 e.getMessage()를 그대로 응답 바디에 실어서 예외 원문(쿼리, 내부 클래스명 등)이
        // 브라우저에 그대로 노출됐음. 서버 로그로만 남기고, 응답은 고정된 안내 문구로 대체.
        log.error("예상하지 못한 오류가 발생했습니다.", e);
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body("일시적인 오류가 발생했어요. 잠시 후 다시 시도해주세요.");
    }

}

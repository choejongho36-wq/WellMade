package com.kdt.wellmade.global.exception;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

import jakarta.validation.ConstraintViolationException;

@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<String> handleIllegalArgument(IllegalArgumentException e) {
        // 사용자 입력 검증 실패 - 메시지 자체가 사용자向 안내 문구이므로 그대로 내려도 안전함
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(e.getMessage());
    }

    /**
     * @Validated 컨트롤러의 @RequestParam 제약 위반(예: month=13). 아래 handleUnexpected에
     * 걸리면 500으로 뭉개지므로 따로 받는다. 위반 메시지는 필드명·제약 이름이 섞인 개발자용
     * 문구라 그대로 내리지 않고 고정 안내로 바꾼다.
     */
    @ExceptionHandler(ConstraintViolationException.class)
    public ResponseEntity<String> handleConstraintViolation(ConstraintViolationException e) {
        log.debug("요청 파라미터 검증 실패: {}", e.getMessage());
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body("요청 값이 올바르지 않아요.");
    }

    /** 타입이 안 맞는 파라미터(예: year=abc). 마찬가지로 서버 잘못이 아니라 요청 잘못이다. */
    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    public ResponseEntity<String> handleTypeMismatch(MethodArgumentTypeMismatchException e) {
        log.debug("요청 파라미터 타입 불일치: {}", e.getName());
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body("요청 값이 올바르지 않아요.");
    }

    /**
     * 유니크 제약 충돌 등. 탭 두 개에서 같은 날 메모를 동시에 저장하면 두 번째가 여기로 온다
     * (WorkoutMemo의 uk_workout_memo_user_date). 서버 오류가 아니라 "이미 처리됐다"는 뜻이므로 409.
     */
    @ExceptionHandler(DataIntegrityViolationException.class)
    public ResponseEntity<String> handleDataIntegrityViolation(DataIntegrityViolationException e) {
        log.warn("데이터 무결성 제약 위반", e);
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body("같은 내용이 이미 저장돼 있어요. 새로고침한 뒤 다시 시도해주세요.");
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

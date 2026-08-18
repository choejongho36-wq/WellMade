package com.kdt.wellmade.global.security;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

import org.junit.jupiter.api.Test;

class OAuth2CodeStoreTest {

    private final OAuth2CodeStore codeStore = new OAuth2CodeStore();

    @Test
    void issuedCodeResolvesToTheSameUserId() {
        String code = codeStore.issue(1L);

        assertEquals(1L, codeStore.consume(code));
    }

    @Test
    void consumingTheSameCodeTwiceReturnsNullOnTheSecondCall() {
        String code = codeStore.issue(1L);
        codeStore.consume(code);

        assertNull(codeStore.consume(code));
    }

    @Test
    void unknownOrNullCodeReturnsNull() {
        assertNull(codeStore.consume("no-such-code"));
        assertNull(codeStore.consume(null));
    }

    // ponytail: 만료(EXPIRE_SECONDS) 분기는 여기서 커버 안 함 - 60초 실제로 기다리거나
    // private 필드를 리플렉션으로 건드려야 해서 비용 대비 효과가 낮음. 만료 로직을
    // 확실히 검증하고 싶어지면 OAuth2CodeStore가 Clock을 주입받게 바꾸고 테스트에서
    // 가짜 시간을 흘려보내는 식으로 업그레이드.
}

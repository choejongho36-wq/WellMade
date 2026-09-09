package com.kdt.wellmade.domain.chat;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

/**
 * "확인해보겠습니다"만 쓰고 끝난 턴을 잡아내는 판별. 놓치면 대화가 멈춘 것처럼 보이고(실측),
 * 과하게 잡으면 멀쩡한 답변을 두 번 만들게 되므로 양쪽을 고정한다.
 */
class PreambleDetectionTest {

    @Test
    void announcementWithoutActionIsPreamble() {
        // 스크린샷 그대로
        assertTrue(ToolCallTextParser.isPreambleOnly(
                "오늘 저녁에 어떤 음식을 먹을지 추천해드릴게요. 최근 섭취 기록을 확인해보겠습니다."));
        assertTrue(ToolCallTextParser.isPreambleOnly("어깨 운동을 찾아볼게요."));
        assertTrue(ToolCallTextParser.isPreambleOnly("기록을 불러오는 중입니다."));
    }

    @Test
    void answerThatCitesDataIsNotPreamble() {
        assertFalse(ToolCallTextParser.isPreambleOnly("어제는 총 1,850kcal 드셨어요. 확인해보니 저녁이 많았네요."));
        assertFalse(ToolCallTextParser.isPreambleOnly("덤벨 스쿼트 3세트 12회부터 해보세요."));
    }

    @Test
    void suggestionToTheUserIsNotPreamble() {
        // "확인해보세요"(권유)는 1인칭 예고가 아니다
        assertFalse(ToolCallTextParser.isPreambleOnly("마이페이지에서 목표를 먼저 확인해보세요."));
    }

    @Test
    void longAnswerIsNotPreambleEvenIfItMentionsChecking() {
        String longAnswer = "확인해보겠습니다. ".repeat(30);
        assertFalse(ToolCallTextParser.isPreambleOnly(longAnswer));
    }

    @Test
    void nullAndBlankAreNotPreamble() {
        assertFalse(ToolCallTextParser.isPreambleOnly(null));
        assertFalse(ToolCallTextParser.isPreambleOnly("   "));
    }
}

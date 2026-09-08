package com.kdt.wellmade.domain.insight;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.kdt.wellmade.global.time.AppTime;

/**
 * 또래 비교의 기준 통계는 "하루 전체 섭취량"이다. 오전 10시에 아침만 기록한 상태를 그대로
 * 비교하면 "또래 평균의 28%"가 나오는데, 적게 먹었다는 뜻이 아니라 하루가 안 끝났다는 뜻이다.
 */
class PeerInsightServiceTest {

    // partialDayNote는 날짜/시각 판단만 하므로 주입 대상이 필요 없다
    private final PeerInsightService service =
            new PeerInsightService(null, null, null, null, new ObjectMapper());

    @Test
    void todayIsMarkedAsAnUnfinishedDay() {
        String note = service.partialDayNote(AppTime.today(), 1);

        assertNotNull(note);
        assertTrue(note.contains("끼니 1건"), note);
        assertTrue(note.contains("참고만"), note);
    }

    @Test
    void pastDayNeedsNoWarning() {
        assertNull(service.partialDayNote(AppTime.today().minusDays(1), 3));
    }

    /** 날짜 기준은 서버 타임존이 아니라 KST다(AppTime) - UTC 서버에서 오전엔 '어제'가 오늘이 된다 */
    @Test
    void futureDateIsNotTreatedAsToday() {
        assertNull(service.partialDayNote(AppTime.today().plusDays(1), 0));
    }
}

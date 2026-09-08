package com.kdt.wellmade.domain.calendar;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Map;

import org.junit.jupiter.api.Test;

import com.fasterxml.jackson.databind.ObjectMapper;

/**
 * 공공데이터포털 특일 정보 응답은 항목 수에 따라 모양이 바뀐다 - 없으면 item 자체가 없고,
 * 하나면 객체, 둘 이상이면 배열이다. 배열만 가정하면 "공휴일이 하나뿐인 달"에서 조용히 비어버린다.
 */
class HolidayServiceParseTest {

    // 외부 호출은 하지 않고 파싱만 보므로 키/클라이언트는 없어도 된다
    private final HolidayService service = new HolidayService("", null, new ObjectMapper());

    @Test
    void parsesMultipleHolidaysFromArray() throws Exception {
        String body = """
                {"response":{"body":{"items":{"item":[
                  {"dateName":"1월1일","locdate":20260101},
                  {"dateName":"설날","locdate":20260217}
                ]},"numOfRows":50,"totalCount":2}}}""";

        Map<String, String> holidays = service.parseResponse(body);

        assertEquals(2, holidays.size());
        assertEquals("1월1일", holidays.get("2026-01-01"));
        assertEquals("설날", holidays.get("2026-02-17"));
    }

    @Test
    void parsesSingleHolidayGivenAsObject() throws Exception {
        String body = """
                {"response":{"body":{"items":{"item":
                  {"dateName":"어린이날","locdate":20260505}
                },"numOfRows":50,"totalCount":1}}}""";

        Map<String, String> holidays = service.parseResponse(body);

        assertEquals(1, holidays.size());
        assertEquals("어린이날", holidays.get("2026-05-05"));
    }

    /** 공휴일이 없는 달. 정상 응답이므로 빈 맵이어야 하고 예외가 나면 안 된다. */
    @Test
    void returnsEmptyWhenMonthHasNoHoliday() throws Exception {
        String body = """
                {"response":{"body":{"items":"","numOfRows":50,"totalCount":0}}}""";

        assertTrue(service.parseResponse(body).isEmpty());
    }

    /** locdate 형식이 깨진 항목은 건너뛰고 나머지는 살린다 */
    @Test
    void skipsItemWithMalformedDate() throws Exception {
        String body = """
                {"response":{"body":{"items":{"item":[
                  {"dateName":"깨진날","locdate":"2026"},
                  {"dateName":"현충일","locdate":20260606}
                ]}}}}""";

        Map<String, String> holidays = service.parseResponse(body);

        assertEquals(1, holidays.size());
        assertEquals("현충일", holidays.get("2026-06-06"));
    }
}

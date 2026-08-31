package com.kdt.wellmade.domain.calendar;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

/**
 * 달력 공휴일 조회 API. 사용자별로 다른 값이 아니라 그냥 로그인만 하면(SecurityConfig 기본 정책)
 * 누구나 조회 가능.
 */
@RestController
@RequestMapping("/api/calendar")
public class HolidayController {

    private final HolidayService holidayService;

    public HolidayController(HolidayService holidayService) {
        this.holidayService = holidayService;
    }

    /** GET /api/calendar/holidays?year=&month= - 해당 월의 공휴일 목록 (달력 칸 표시용) */
    @GetMapping("/holidays")
    public Map<String, String> getHolidays(@RequestParam int year, @RequestParam int month) {
        return holidayService.getHolidays(year, month);
    }
}

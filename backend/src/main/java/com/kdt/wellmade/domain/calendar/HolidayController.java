package com.kdt.wellmade.domain.calendar;

import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;

import java.util.Map;

/**
 * 달력 공휴일 조회 API. 사용자별로 다른 값이 아니라 그냥 로그인만 하면(SecurityConfig 기본 정책)
 * 누구나 조회 가능.
 */
@RestController
@RequestMapping("/api/calendar")
// year/month를 검증 없이 받으면 month=13 같은 값이 LocalDate/외부 API까지 그대로 흘러가서
// 500이 난다. @Validated가 있어야 @RequestParam에 붙인 제약이 실제로 검사된다.
@Validated
public class HolidayController {

    private final HolidayService holidayService;

    public HolidayController(HolidayService holidayService) {
        this.holidayService = holidayService;
    }

    /** GET /api/calendar/holidays?year=&month= - 해당 월의 공휴일 목록 (달력 칸 표시용) */
    @GetMapping("/holidays")
    public Map<String, String> getHolidays(
            @RequestParam @Min(2000) @Max(2100) int year,
            @RequestParam @Min(1) @Max(12) int month
    ) {
        return holidayService.getHolidays(year, month);
    }
}

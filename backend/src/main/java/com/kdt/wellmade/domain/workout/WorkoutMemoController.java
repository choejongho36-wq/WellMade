package com.kdt.wellmade.domain.workout;

import java.time.LocalDate;
import java.util.Map;

import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.validation.annotation.Validated;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.kdt.wellmade.domain.user.UserService;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;

/**
 * 날짜별 운동 메모 API. 캘린더에서 날짜를 고르면 그 날 메모를 읽고, 저장하면 덮어쓴다.
 * 내용을 비워서 저장하면 삭제된다(WorkoutMemoService.save 참고).
 */
@RestController
@RequestMapping("/api/users/me/workout-memos")
@Validated
public class WorkoutMemoController {

    private final WorkoutMemoService workoutMemoService;
    private final UserService userService;

    public WorkoutMemoController(WorkoutMemoService workoutMemoService, UserService userService) {
        this.workoutMemoService = workoutMemoService;
        this.userService = userService;
    }

    @GetMapping("/{date}")
    public Map<String, String> get(
            @AuthenticationPrincipal Long userId,
            @PathVariable @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate date
    ) {
        return Map.of("date", date.toString(), "content", workoutMemoService.get(userService.getUser(userId), date));
    }

    @PutMapping("/{date}")
    public Map<String, String> save(
            @AuthenticationPrincipal Long userId,
            @PathVariable @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate date,
            @RequestBody WorkoutMemoRequest request
    ) {
        String saved = workoutMemoService.save(userService.getUser(userId), date, request.content());
        return Map.of("date", date.toString(), "content", saved);
    }

    /** 캘린더가 "메모 있는 날"을 표시하려고 한 달치를 한 번에 가져간다 */
    @GetMapping
    public Map<String, String> month(
            @AuthenticationPrincipal Long userId,
            @RequestParam @Min(2000) @Max(2100) int year,
            @RequestParam @Min(1) @Max(12) int month
    ) {
        return workoutMemoService.getMonth(userService.getUser(userId), year, month);
    }
}

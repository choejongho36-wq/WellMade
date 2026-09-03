package com.kdt.wellmade.domain.workout;

import java.time.LocalDate;
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.kdt.wellmade.domain.user.User;

@Service
public class WorkoutMemoService {

    private final WorkoutMemoRepository workoutMemoRepository;

    public WorkoutMemoService(WorkoutMemoRepository workoutMemoRepository) {
        this.workoutMemoRepository = workoutMemoRepository;
    }

    @Transactional(readOnly = true)
    public String get(User user, LocalDate date) {
        return workoutMemoRepository.findByUserAndMemoDate(user, date)
                .map(WorkoutMemo::getContent)
                .orElse("");
    }

    /**
     * 같은 날 메모를 덮어쓴다. 내용을 비우면 저장이 아니라 삭제다 - 빈 문자열 행을 남겨두면
     * 캘린더의 "메모 있는 날" 표시가 거짓으로 켜진다.
     */
    @Transactional
    public String save(User user, LocalDate date, String rawContent) {
        String content = rawContent == null ? "" : rawContent.trim();
        if (content.length() > WorkoutMemo.MAX_LENGTH) {
            content = content.substring(0, WorkoutMemo.MAX_LENGTH);
        }

        WorkoutMemo existing = workoutMemoRepository.findByUserAndMemoDate(user, date).orElse(null);
        if (content.isEmpty()) {
            if (existing != null) {
                workoutMemoRepository.delete(existing);
            }
            return "";
        }

        if (existing != null) {
            existing.updateContent(content);
        } else {
            workoutMemoRepository.save(
                    WorkoutMemo.builder().user(user).memoDate(date).content(content).build());
        }
        return content;
    }

    /** 한 달 중 메모가 있는 날짜 -> 내용 (캘린더 표시용) */
    @Transactional(readOnly = true)
    public Map<String, String> getMonth(User user, int year, int month) {
        LocalDate from = LocalDate.of(year, month, 1);
        LocalDate to = from.withDayOfMonth(from.lengthOfMonth());

        Map<String, String> result = new LinkedHashMap<>();
        for (WorkoutMemo memo : workoutMemoRepository.findByUserAndMemoDateBetween(user, from, to)) {
            result.put(memo.getMemoDate().toString(), memo.getContent());
        }
        return result;
    }
}

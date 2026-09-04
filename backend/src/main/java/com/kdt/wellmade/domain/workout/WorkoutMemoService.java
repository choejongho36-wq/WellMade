package com.kdt.wellmade.domain.workout;

import java.time.LocalDate;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.kdt.wellmade.domain.user.User;

@Service
public class WorkoutMemoService {

    /**
     * 월 조회에서 내려보낼 미리보기 길이. 캘린더는 "메모 있음" 점만 그리고 내용은 날짜를 고를 때
     * 따로 받아가므로, 한 달치 본문(최대 31 x 1000자)을 통째로 실어 보낼 이유가 없다.
     * 잘라낸 앞부분은 달력 칸의 툴팁(title)으로 쓴다.
     */
    static final int MONTH_PREVIEW_LENGTH = 30;

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

    /** 한 달 중 메모가 있는 날짜 -> 앞부분 미리보기 (캘린더 표시용) */
    @Transactional(readOnly = true)
    public Map<String, String> getMonth(User user, int year, int month) {
        LocalDate from = LocalDate.of(year, month, 1);
        LocalDate to = from.withDayOfMonth(from.lengthOfMonth());

        Map<String, String> result = new LinkedHashMap<>();
        for (WorkoutMemo memo : workoutMemoRepository.findByUserAndMemoDateBetween(user, from, to)) {
            result.put(memo.getMemoDate().toString(), preview(memo.getContent()));
        }
        return result;
    }

    /**
     * 날짜 범위의 메모 원문. 챗봇 운동 추천이 "최근에 무슨 부위를 했는지" 읽는 데 쓴다 -
     * 여기서는 미리보기가 아니라 원문이 필요하다(부위 키워드가 뒤쪽에 있을 수 있다).
     */
    @Transactional(readOnly = true)
    public List<Map<String, String>> getBetween(User user, LocalDate from, LocalDate to) {
        return workoutMemoRepository.findByUserAndMemoDateBetween(user, from, to).stream()
                .map(memo -> Map.of("date", memo.getMemoDate().toString(), "text", memo.getContent()))
                .toList();
    }

    static String preview(String content) {
        if (content == null) {
            return "";
        }
        // 줄바꿈이 섞이면 툴팁에서 지저분해서 한 줄로 편다
        String flat = content.replaceAll("\\s+", " ").trim();
        return flat.length() <= MONTH_PREVIEW_LENGTH ? flat : flat.substring(0, MONTH_PREVIEW_LENGTH) + "...";
    }
}

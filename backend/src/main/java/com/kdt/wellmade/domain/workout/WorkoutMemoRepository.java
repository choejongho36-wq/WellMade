package com.kdt.wellmade.domain.workout;

import java.time.LocalDate;
import java.util.List;
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

import com.kdt.wellmade.domain.user.User;

public interface WorkoutMemoRepository extends JpaRepository<WorkoutMemo, Long> {

    Optional<WorkoutMemo> findByUserAndMemoDate(User user, LocalDate memoDate);

    /** 캘린더에 "메모 있는 날"을 표시하려고 한 달치를 한 번에 읽는다 */
    List<WorkoutMemo> findByUserAndMemoDateBetween(User user, LocalDate from, LocalDate to);

    // 탈퇴 시 UserService.withdraw()가 순서대로 지운다(FK cascade를 안 쓰는 기존 방식과 동일)
    void deleteByUser(User user);
}

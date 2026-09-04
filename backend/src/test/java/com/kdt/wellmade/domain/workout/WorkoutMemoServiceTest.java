package com.kdt.wellmade.domain.workout;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.time.LocalDate;
import java.util.List;
import java.util.Optional;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import com.kdt.wellmade.domain.user.User;

/**
 * 메모 저장은 "빈 내용이면 삭제"라는 규칙이 있어서 저장/삭제가 한 메서드에 섞여 있다.
 * 그 분기가 뒤집히면 캘린더의 "메모 있는 날" 점이 거짓으로 켜지거나(빈 행이 남아서),
 * 지우려던 메모가 안 지워진다.
 */
class WorkoutMemoServiceTest {

    private final WorkoutMemoRepository repository = mock(WorkoutMemoRepository.class);
    private final WorkoutMemoService service = new WorkoutMemoService(repository);
    private final User user = mock(User.class);
    private final LocalDate date = LocalDate.of(2026, 9, 4);

    @Test
    void blankContentDeletesExistingMemo() {
        WorkoutMemo existing = WorkoutMemo.builder().user(user).memoDate(date).content("스쿼트 60kg").build();
        when(repository.findByUserAndMemoDate(user, date)).thenReturn(Optional.of(existing));

        // 공백만 남긴 것도 "지워달라"는 뜻이다
        assertEquals("", service.save(user, date, "   "));

        verify(repository).delete(existing);
        verify(repository, never()).save(any());
    }

    @Test
    void blankContentWithoutExistingMemoDoesNothing() {
        when(repository.findByUserAndMemoDate(user, date)).thenReturn(Optional.empty());

        assertEquals("", service.save(user, date, ""));

        verify(repository, never()).delete(any());
        verify(repository, never()).save(any());
    }

    /** content 컬럼이 1000자라 넘치면 저장 자체가 실패한다. 잘라서 넣고, 잘린 값을 그대로 돌려준다. */
    @Test
    void tooLongContentIsTruncatedToMaxLength() {
        when(repository.findByUserAndMemoDate(user, date)).thenReturn(Optional.empty());
        String tooLong = "가".repeat(WorkoutMemo.MAX_LENGTH + 200);

        String saved = service.save(user, date, tooLong);

        assertEquals(WorkoutMemo.MAX_LENGTH, saved.length());
        ArgumentCaptor<WorkoutMemo> captor = ArgumentCaptor.forClass(WorkoutMemo.class);
        verify(repository).save(captor.capture());
        assertEquals(WorkoutMemo.MAX_LENGTH, captor.getValue().getContent().length());
    }

    @Test
    void existingMemoIsOverwrittenInPlace() {
        WorkoutMemo existing = WorkoutMemo.builder().user(user).memoDate(date).content("예전 내용").build();
        when(repository.findByUserAndMemoDate(user, date)).thenReturn(Optional.of(existing));

        assertEquals("새 내용", service.save(user, date, " 새 내용 "));

        assertEquals("새 내용", existing.getContent());
        // 이미 영속 상태라 다시 save할 필요가 없다(더티 체킹)
        verify(repository, never()).save(any());
    }

    /** 월 조회는 점을 찍는 용도라 본문 전체가 아니라 툴팁용 앞부분만 내려간다 */
    @Test
    void monthViewReturnsShortPreviewInsteadOfFullBody() {
        WorkoutMemo memo = WorkoutMemo.builder().user(user).memoDate(date)
                .content("하체\n스쿼트 60kg 5x5, 레그프레스 100kg 4x10, 런닝 20분").build();
        when(repository.findByUserAndMemoDateBetween(user, LocalDate.of(2026, 9, 1), LocalDate.of(2026, 9, 30)))
                .thenReturn(List.of(memo));

        Map<String, String> month = service.getMonth(user, 2026, 9);

        String preview = month.get("2026-09-04");
        assertEquals(WorkoutMemoService.MONTH_PREVIEW_LENGTH + "...".length(), preview.length());
        assertEquals("하체 스쿼트 60kg 5x5, 레그프레스 100kg 4...", preview);
    }
}

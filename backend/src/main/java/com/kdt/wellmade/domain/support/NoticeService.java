package com.kdt.wellmade.domain.support;

import java.util.List;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import lombok.RequiredArgsConstructor;

@Service
@RequiredArgsConstructor
public class NoticeService {

    private final NoticeRepository noticeRepository;

    public List<NoticeResponse> list() {
        return noticeRepository.findAllByOrderByPinnedDescCreatedAtDescIdDesc().stream()
                .map(NoticeResponse::of)
                .toList();
    }

    public NoticeResponse get(Long noticeId) {
        return NoticeResponse.of(findNotice(noticeId));
    }

    // --- 관리자 전용 ---

    public Page<NoticeResponse> adminList(Pageable pageable) {
        return noticeRepository.findAllByOrderByPinnedDescCreatedAtDescIdDesc(pageable).map(NoticeResponse::of);
    }

    @Transactional
    public NoticeResponse create(NoticeRequest request) {
        validate(request);
        Notice notice = noticeRepository.save(Notice.builder()
                .title(request.title())
                .content(request.content())
                .pinned(request.pinned())
                .build());
        return NoticeResponse.of(notice);
    }

    @Transactional
    public NoticeResponse update(Long noticeId, NoticeRequest request) {
        validate(request);
        Notice notice = findNotice(noticeId);
        notice.update(request.title(), request.content(), request.pinned());
        return NoticeResponse.of(notice);
    }

    @Transactional
    public void delete(Long noticeId) {
        noticeRepository.delete(findNotice(noticeId));
    }

    private Notice findNotice(Long noticeId) {
        return noticeRepository.findById(noticeId)
                .orElseThrow(() -> new IllegalArgumentException("공지사항을 찾을 수 없습니다."));
    }

    private void validate(NoticeRequest request) {
        if (request.title() == null || request.title().isBlank()) {
            throw new IllegalArgumentException("제목을 입력해주세요.");
        }
        if (request.content() == null || request.content().isBlank()) {
            throw new IllegalArgumentException("내용을 입력해주세요.");
        }
    }
}

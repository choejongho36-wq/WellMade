package com.kdt.wellmade.domain.support;

import java.util.List;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.kdt.wellmade.domain.user.User;

import lombok.RequiredArgsConstructor;

/**
 * 고객센터 1:1 문의 게시판. 전체 회원에게 목록이 공개되는 게시판 형태라(비공개 티켓이 아님),
 * 비밀글이 아닌 이상 다른 회원의 글도 제목/본문을 볼 수 있다 - Roomie(다른 팀 프로젝트) 문의
 * 게시판과 같은 방식.
 */
@Service
@RequiredArgsConstructor
public class InquiryService {

    private final InquiryRepository inquiryRepository;

    public List<InquiryResponse> list(Long viewerUserId) {
        return inquiryRepository.findAllByOrderByCreatedAtDesc().stream()
                .map(i -> InquiryResponse.of(i, viewerUserId, false))
                .toList();
    }

    public InquiryResponse get(Long inquiryId, Long viewerUserId) {
        return InquiryResponse.of(findInquiry(inquiryId), viewerUserId, false);
    }

    public InquiryResponse create(User user, InquiryRequest request) {
        validate(request);
        Inquiry inquiry = inquiryRepository.save(Inquiry.builder()
                .user(user)
                .title(request.title())
                .category(request.category())
                .content(request.content())
                .secret(request.secret())
                .build());
        return InquiryResponse.of(inquiry, user.getId(), false);
    }

    @Transactional
    public InquiryResponse update(User user, Long inquiryId, InquiryRequest request) {
        validate(request);
        Inquiry inquiry = findInquiry(inquiryId);
        if (!inquiry.getUser().getId().equals(user.getId())) {
            throw new IllegalArgumentException("본인이 작성한 문의만 수정할 수 있습니다.");
        }
        inquiry.update(request.title(), request.category(), request.content(), request.secret());
        return InquiryResponse.of(inquiry, user.getId(), false);
    }

    @Transactional
    public void delete(User user, Long inquiryId) {
        Inquiry inquiry = findInquiry(inquiryId);
        if (!inquiry.getUser().getId().equals(user.getId())) {
            throw new IllegalArgumentException("본인이 작성한 문의만 삭제할 수 있습니다.");
        }
        inquiryRepository.delete(inquiry);
    }

    // --- 관리자 전용 ---

    public Page<InquiryResponse> adminList(InquiryStatus status, Pageable pageable) {
        Page<Inquiry> page = status != null
                ? inquiryRepository.findByStatusOrderByCreatedAtDesc(status, pageable)
                : inquiryRepository.findAllByOrderByCreatedAtDesc(pageable);
        return page.map(i -> InquiryResponse.of(i, null, true));
    }

    public InquiryResponse adminGet(Long inquiryId) {
        return InquiryResponse.of(findInquiry(inquiryId), null, true);
    }

    @Transactional
    public InquiryResponse answer(Long inquiryId, String answer) {
        if (answer == null || answer.isBlank()) {
            throw new IllegalArgumentException("답변 내용을 입력해주세요.");
        }
        Inquiry inquiry = findInquiry(inquiryId);
        inquiry.answer(answer);
        return InquiryResponse.of(inquiry, null, true);
    }

    @Transactional
    public InquiryResponse deleteAnswer(Long inquiryId) {
        Inquiry inquiry = findInquiry(inquiryId);
        inquiry.clearAnswer();
        return InquiryResponse.of(inquiry, null, true);
    }

    @Transactional
    public void adminDelete(Long inquiryId) {
        inquiryRepository.delete(findInquiry(inquiryId));
    }

    private Inquiry findInquiry(Long inquiryId) {
        return inquiryRepository.findById(inquiryId)
                .orElseThrow(() -> new IllegalArgumentException("문의를 찾을 수 없습니다."));
    }

    private void validate(InquiryRequest request) {
        if (request.title() == null || request.title().isBlank()) {
            throw new IllegalArgumentException("제목을 입력해주세요.");
        }
        if (request.content() == null || request.content().isBlank()) {
            throw new IllegalArgumentException("문의 내용을 입력해주세요.");
        }
        if (request.category() == null) {
            throw new IllegalArgumentException("분류를 선택해주세요.");
        }
    }
}

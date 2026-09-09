package com.kdt.wellmade.domain.support;

import java.util.List;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import lombok.RequiredArgsConstructor;

@Service
@RequiredArgsConstructor
public class FaqService {

    private final FaqRepository faqRepository;

    public List<FaqResponse> list() {
        return faqRepository.findAllByOrderByDisplayOrderAscCreatedAtDescIdDesc().stream()
                .map(FaqResponse::of)
                .toList();
    }

    // --- 관리자 전용 ---

    @Transactional
    public FaqResponse create(FaqRequest request) {
        validate(request);
        Faq faq = faqRepository.save(Faq.builder()
                .question(request.question())
                .answer(request.answer())
                .displayOrder(request.displayOrder())
                .build());
        return FaqResponse.of(faq);
    }

    @Transactional
    public FaqResponse update(Long faqId, FaqRequest request) {
        validate(request);
        Faq faq = findFaq(faqId);
        faq.update(request.question(), request.answer(), request.displayOrder());
        return FaqResponse.of(faq);
    }

    @Transactional
    public void delete(Long faqId) {
        faqRepository.delete(findFaq(faqId));
    }

    private Faq findFaq(Long faqId) {
        return faqRepository.findById(faqId)
                .orElseThrow(() -> new IllegalArgumentException("FAQ를 찾을 수 없습니다."));
    }

    private void validate(FaqRequest request) {
        if (request.question() == null || request.question().isBlank()) {
            throw new IllegalArgumentException("질문을 입력해주세요.");
        }
        if (request.answer() == null || request.answer().isBlank()) {
            throw new IllegalArgumentException("답변을 입력해주세요.");
        }
    }
}

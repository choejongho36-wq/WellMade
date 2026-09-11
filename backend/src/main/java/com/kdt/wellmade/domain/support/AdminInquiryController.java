package com.kdt.wellmade.domain.support;

import java.util.List;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import lombok.RequiredArgsConstructor;

/** 1:1 문의 관리자 API. 답변 작성/삭제, 전체 목록 조회(비밀글 포함)를 담당한다. */
@RestController
@RequestMapping("/api/admin/inquiries")
@RequiredArgsConstructor
public class AdminInquiryController {

    private static final int PAGE_SIZE = 20;

    private final InquiryService inquiryService;

    public record InquiryListResponse(
            List<InquiryResponse> content, int page, int totalPages, long totalElements) {
        static InquiryListResponse from(Page<InquiryResponse> page) {
            return new InquiryListResponse(
                    page.getContent(), page.getNumber(), page.getTotalPages(), page.getTotalElements());
        }
    }

    @GetMapping
    public InquiryListResponse list(
            @RequestParam(value = "status", required = false) InquiryStatus status,
            @RequestParam(value = "page", defaultValue = "0") int page
    ) {
        return InquiryListResponse.from(inquiryService.adminList(status, PageRequest.of(page, PAGE_SIZE)));
    }

    @GetMapping("/{id}")
    public InquiryResponse get(@PathVariable Long id) {
        return inquiryService.adminGet(id);
    }

    @PostMapping("/{id}/answer")
    public InquiryResponse answer(@PathVariable Long id, @RequestBody InquiryAnswerRequest request) {
        return inquiryService.answer(id, request.answer());
    }

    @DeleteMapping("/{id}/answer")
    public InquiryResponse deleteAnswer(@PathVariable Long id) {
        return inquiryService.deleteAnswer(id);
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable Long id) {
        inquiryService.adminDelete(id);
        return ResponseEntity.noContent().build();
    }
}

package com.kdt.wellmade.domain.support;

import java.util.List;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import lombok.RequiredArgsConstructor;

/** 공지사항 관리자 API. 작성/수정/삭제를 담당한다. */
@RestController
@RequestMapping("/api/admin/notices")
@RequiredArgsConstructor
public class AdminNoticeController {

    private static final int PAGE_SIZE = 20;

    private final NoticeService noticeService;

    public record NoticeListResponse(
            List<NoticeResponse> content, int page, int totalPages, long totalElements) {
        static NoticeListResponse from(Page<NoticeResponse> page) {
            return new NoticeListResponse(
                    page.getContent(), page.getNumber(), page.getTotalPages(), page.getTotalElements());
        }
    }

    @GetMapping
    public NoticeListResponse list(@RequestParam(value = "page", defaultValue = "0") int page) {
        return NoticeListResponse.from(noticeService.adminList(PageRequest.of(page, PAGE_SIZE)));
    }

    @GetMapping("/{id}")
    public NoticeResponse get(@PathVariable Long id) {
        return noticeService.get(id);
    }

    @PostMapping
    public NoticeResponse create(@RequestBody NoticeRequest request) {
        return noticeService.create(request);
    }

    @PutMapping("/{id}")
    public NoticeResponse update(@PathVariable Long id, @RequestBody NoticeRequest request) {
        return noticeService.update(id, request);
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable Long id) {
        noticeService.delete(id);
        return ResponseEntity.noContent().build();
    }
}

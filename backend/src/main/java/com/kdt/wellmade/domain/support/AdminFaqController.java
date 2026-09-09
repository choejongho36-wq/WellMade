package com.kdt.wellmade.domain.support;

import java.util.List;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import lombok.RequiredArgsConstructor;

/** FAQ 관리자 API. 작성/수정/삭제를 담당한다(목록 조회는 공개 API와 동일해 그대로 재사용). */
@RestController
@RequestMapping("/api/admin/faqs")
@RequiredArgsConstructor
public class AdminFaqController {

    private final FaqService faqService;

    @GetMapping
    public List<FaqResponse> list() {
        return faqService.list();
    }

    @PostMapping
    public FaqResponse create(@RequestBody FaqRequest request) {
        return faqService.create(request);
    }

    @PutMapping("/{id}")
    public FaqResponse update(@PathVariable Long id, @RequestBody FaqRequest request) {
        return faqService.update(id, request);
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable Long id) {
        faqService.delete(id);
        return ResponseEntity.noContent().build();
    }
}

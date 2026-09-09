package com.kdt.wellmade.domain.support;

import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import lombok.RequiredArgsConstructor;

/** FAQ 조회 API (일반 회원용). 작성/수정/삭제는 관리자 API(/api/admin/**) 쪽에서 처리한다. */
@RestController
@RequestMapping("/api/faqs")
@RequiredArgsConstructor
public class FaqController {

    private final FaqService faqService;

    @GetMapping
    public List<FaqResponse> list() {
        return faqService.list();
    }
}

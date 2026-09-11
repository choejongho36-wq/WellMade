package com.kdt.wellmade.domain.support;

import java.util.List;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.kdt.wellmade.domain.user.UserService;

/**
 * 1:1 문의 게시판 API (일반 회원용). 전체 회원에게 목록이 공개되는 게시판이라
 * /api/users/me/... 가 아닌 /api/inquiries 로 둔다 - InquiryService 클래스 설명 참고.
 */
@RestController
@RequestMapping("/api/inquiries")
public class InquiryController {

    private final InquiryService inquiryService;
    private final UserService userService;

    public InquiryController(InquiryService inquiryService, UserService userService) {
        this.inquiryService = inquiryService;
        this.userService = userService;
    }

    @GetMapping
    public List<InquiryResponse> list(@AuthenticationPrincipal Long userId) {
        return inquiryService.list(userId);
    }

    @GetMapping("/{id}")
    public InquiryResponse get(@AuthenticationPrincipal Long userId, @PathVariable Long id) {
        return inquiryService.get(id, userId);
    }

    @PostMapping
    public InquiryResponse create(@AuthenticationPrincipal Long userId, @RequestBody InquiryRequest request) {
        return inquiryService.create(userService.getUser(userId), request);
    }

    @PutMapping("/{id}")
    public InquiryResponse update(
            @AuthenticationPrincipal Long userId, @PathVariable Long id, @RequestBody InquiryRequest request
    ) {
        return inquiryService.update(userService.getUser(userId), id, request);
    }

    @DeleteMapping("/{id}")
    public void delete(@AuthenticationPrincipal Long userId, @PathVariable Long id) {
        inquiryService.delete(userService.getUser(userId), id);
    }
}

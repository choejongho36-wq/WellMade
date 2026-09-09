package com.kdt.wellmade.domain.support;

import java.time.LocalDateTime;

/**
 * 문의 게시판 응답. 비밀글이고 조회자가 작성자 본인/관리자가 아니면 content/answer를 null로
 * 감춘 채 내려간다(hidden 플래그로 화면이 "비밀글입니다" 안내를 보여줄 수 있게 함).
 */
public record InquiryResponse(
        Long id,
        String authorEmail,
        String title,
        InquiryCategory category,
        String content,
        InquiryStatus status,
        String answer,
        boolean secret,
        boolean hidden,
        boolean mine,
        LocalDateTime createdAt,
        LocalDateTime answeredAt
) {
    public static InquiryResponse of(Inquiry i, Long viewerUserId, boolean viewerIsAdmin) {
        boolean mine = i.getUser().getId().equals(viewerUserId);
        boolean canViewContent = viewerIsAdmin || mine;
        boolean hidden = i.isSecret() && !canViewContent;
        return new InquiryResponse(
                i.getId(),
                i.getUser().getEmail(),
                i.getTitle(),
                i.getCategory(),
                hidden ? null : i.getContent(),
                i.getStatus(),
                hidden ? null : i.getAnswer(),
                i.isSecret(),
                hidden,
                mine,
                i.getCreatedAt(),
                i.getAnsweredAt());
    }
}

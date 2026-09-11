package com.kdt.wellmade.domain.support;

import java.time.LocalDateTime;

public record FaqResponse(Long id, String question, String answer, int displayOrder, LocalDateTime createdAt) {
    public static FaqResponse of(Faq faq) {
        return new FaqResponse(faq.getId(), faq.getQuestion(), faq.getAnswer(), faq.getDisplayOrder(), faq.getCreatedAt());
    }
}

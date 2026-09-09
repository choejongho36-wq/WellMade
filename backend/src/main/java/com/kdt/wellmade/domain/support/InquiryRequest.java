package com.kdt.wellmade.domain.support;

public record InquiryRequest(String title, InquiryCategory category, String content, boolean secret) {}

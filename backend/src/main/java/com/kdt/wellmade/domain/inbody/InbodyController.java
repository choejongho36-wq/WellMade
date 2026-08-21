package com.kdt.wellmade.domain.inbody;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
 
import java.io.IOException;
 

@RestController
public class InbodyController {
 
    private final InbodyService inbodyService;
 
    public InbodyController(InbodyService inbodyService) {
        this.inbodyService = inbodyService;
    }
 
    @PostMapping("/api/test/ocr")
    public InbodyResult testOcr(@RequestParam("image") MultipartFile image) {
        try {
            return inbodyService.extract(image);
        } catch (IOException e) {
            throw new RuntimeException("OCR 실패: " + e.getMessage(), e);
        }
    }
}
 
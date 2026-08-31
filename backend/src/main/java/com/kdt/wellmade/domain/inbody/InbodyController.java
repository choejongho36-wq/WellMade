package com.kdt.wellmade.domain.inbody;

import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import com.kdt.wellmade.domain.user.User;
import com.kdt.wellmade.domain.user.UserService;

import java.io.IOException;
import java.util.List;


@RestController
public class InbodyController {

    private final InbodyService inbodyService;
    private final UserService userService;

    public InbodyController(InbodyService inbodyService, UserService userService) {
        this.inbodyService = inbodyService;
        this.userService = userService;
    }

    @PostMapping("/api/users/me/inbody/extract")
    public InbodyResult extractMyInbody(@RequestParam("image") MultipartFile image) {
        try {
            return inbodyService.extract(image);
        } catch (IOException e) {
            throw new RuntimeException("인바디 이미지 인식 실패: " + e.getMessage(), e);
        }
    }

    @PostMapping("/api/users/me/inbody")
    public InbodyRecordResponse confirmMyInbody(@AuthenticationPrincipal Long userId,
                                                 @RequestBody InbodyConfirmRequest request) {
        User user = userService.getUser(userId);
        return InbodyRecordResponse.from(inbodyService.save(user, request));
    }

    @GetMapping("/api/users/me/inbody/history")
    public List<InbodyRecordResponse> getMyInbodyHistory(@AuthenticationPrincipal Long userId) {
        User user = userService.getUser(userId);
        return inbodyService.getAllHistory(user).stream()
                .map(InbodyRecordResponse::from)
                .toList();
    }

    @GetMapping("/api/users/me/inbody/latest")
    public ResponseEntity<InbodyRecordResponse> getMyLatestInbody(@AuthenticationPrincipal Long userId) {
        User user = userService.getUser(userId);
        return inbodyService.getLatest(user)
                .map(record -> ResponseEntity.ok(InbodyRecordResponse.from(record)))
                .orElseGet(() -> ResponseEntity.noContent().build());
    }
}

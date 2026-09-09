package com.kdt.wellmade.domain.report;

import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import com.kdt.wellmade.domain.user.User;
import com.kdt.wellmade.domain.user.UserService;

/**
 * 사진측정/세션리포트 화면의 "신고" 버튼이 호출하는 API. 신고 사유 카테고리는
 * ReportReasonCategory 값(FALSE_POSITIVE/FALSE_NEGATIVE/POSE_DETECTION_ERROR/OTHER) 중
 * 하나를 문자열로 받는다 — OTHER면 reasonDetail이 반드시 있어야 한다.
 */
@RestController
public class PoseReportController {

    private final PoseReportService poseReportService;
    private final UserService userService;

    public PoseReportController(PoseReportService poseReportService, UserService userService) {
        this.poseReportService = poseReportService;
        this.userService = userService;
    }

    @PostMapping("/api/users/me/reports")
    public ResponseEntity<Void> submitReport(
            @AuthenticationPrincipal Long userId,
            @RequestParam("sourceType") ReportSourceType sourceType,
            @RequestParam(value = "sourceId", required = false) String sourceId,
            @RequestParam("file") MultipartFile file,
            @RequestParam("reasonCategory") ReportReasonCategory reasonCategory,
            @RequestParam(value = "reasonDetail", required = false) String reasonDetail,
            @RequestParam(value = "judgmentSnapshot", required = false) String judgmentSnapshot) {
        User user = userService.getUser(userId);
        poseReportService.submit(user, sourceType, sourceId, file, reasonCategory, reasonDetail, judgmentSnapshot);
        return ResponseEntity.ok().build();
    }
}

package com.kdt.wellmade.domain.report;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

import com.kdt.wellmade.domain.user.User;

@Service
public class PoseReportService {

    private final PoseReportRepository poseReportRepository;
    private final S3StorageService s3StorageService;

    public PoseReportService(PoseReportRepository poseReportRepository, S3StorageService s3StorageService) {
        this.poseReportRepository = poseReportRepository;
        this.s3StorageService = s3StorageService;
    }

    @Transactional
    public PoseReport submit(User user, ReportSourceType sourceType, String sourceId, MultipartFile file,
                              ReportReasonCategory reasonCategory, String reasonDetail, String aiJudgmentSnapshot) {
        if (reasonCategory == ReportReasonCategory.OTHER && (reasonDetail == null || reasonDetail.isBlank())) {
            throw new IllegalArgumentException("기타 사유를 선택했다면 사유를 입력해야 합니다.");
        }
        String s3Key;
        try {
            s3Key = s3StorageService.upload(file, sourceType);
        } catch (IOException e) {
            throw new RuntimeException("신고 파일 업로드에 실패했습니다: " + e.getMessage(), e);
        }

        PoseReport report = PoseReport.builder()
                .user(user)
                .sourceType(sourceType)
                .sourceId(sourceId)
                .s3Key(s3Key)
                .aiJudgmentSnapshot(aiJudgmentSnapshot)
                .reasonCategory(reasonCategory)
                .reasonDetail(reasonCategory == ReportReasonCategory.OTHER ? reasonDetail : null)
                .build();
        return poseReportRepository.save(report);
    }

    public Page<PoseReport> list(ReportStatus status, Pageable pageable) {
        return status == null
                ? poseReportRepository.findAllByOrderByCreatedAtDesc(pageable)
                : poseReportRepository.findByStatusOrderByCreatedAtDesc(status, pageable);
    }

    public PoseReport get(Long id) {
        return poseReportRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("신고를 찾을 수 없습니다: " + id));
    }

    public long countByStatus(ReportStatus status) {
        return poseReportRepository.countByStatus(status);
    }

    public String presignedUrlFor(PoseReport report) {
        return s3StorageService.presignedGetUrl(report.getS3Key());
    }

    @Transactional
    public void approve(Long id, String adminLoginId) {
        PoseReport report = get(id);
        report.approve(adminLoginId);
    }

    /** 거절 시 원본까지 즉시 삭제 — 불필요한 개인 촬영 데이터를 남겨두지 않는다는 원칙. */
    @Transactional
    public void reject(Long id, String adminLoginId) {
        PoseReport report = get(id);
        s3StorageService.delete(report.getS3Key());
        report.reject(adminLoginId);
    }

    /**
     * 승인된 신고 전체를 zip으로 묶어준다 — 관리자가 이걸 받아 로컬에서 오프라인 스크립트로
     * 좌표추출/DTW 템플릿 재계산에 쓴다. manifest.json에 판정 스냅샷/사유를, README.txt에
     * 다음 단계 안내를 같이 넣어 압축 파일만으로 무슨 작업인지 알 수 있게 한다.
     */
    public byte[] exportApprovedZip() throws IOException {
        List<PoseReport> approved = poseReportRepository.findByStatusOrderByCreatedAtAsc(ReportStatus.APPROVED);

        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (ZipOutputStream zip = new ZipOutputStream(buffer)) {
            StringBuilder manifest = new StringBuilder("[\n");
            for (int i = 0; i < approved.size(); i++) {
                PoseReport report = approved.get(i);
                String entryName = report.getId() + "_" + fileNameOf(report.getS3Key());

                zip.putNextEntry(new ZipEntry(entryName));
                zip.write(s3StorageService.download(report.getS3Key()));
                zip.closeEntry();

                manifest.append("  {\n")
                        .append("    \"reportId\": ").append(report.getId()).append(",\n")
                        .append("    \"file\": \"").append(escape(entryName)).append("\",\n")
                        .append("    \"sourceType\": \"").append(report.getSourceType()).append("\",\n")
                        .append("    \"sourceId\": ").append(quoteOrNull(report.getSourceId())).append(",\n")
                        .append("    \"reasonCategory\": \"").append(report.getReasonCategory()).append("\",\n")
                        .append("    \"reasonDetail\": ").append(quoteOrNull(report.getReasonDetail())).append(",\n")
                        .append("    \"aiJudgmentSnapshot\": ").append(quoteOrNull(report.getAiJudgmentSnapshot())).append(",\n")
                        .append("    \"reportedAt\": \"").append(report.getCreatedAt()).append("\",\n")
                        .append("    \"approvedBy\": ").append(quoteOrNull(report.getReviewedBy())).append("\n")
                        .append("  }").append(i < approved.size() - 1 ? ",\n" : "\n");
            }
            manifest.append("]\n");

            zip.putNextEntry(new ZipEntry("manifest.json"));
            zip.write(manifest.toString().getBytes(StandardCharsets.UTF_8));
            zip.closeEntry();

            zip.putNextEntry(new ZipEntry("README.txt"));
            zip.write(README.getBytes(StandardCharsets.UTF_8));
            zip.closeEntry();
        }
        return buffer.toByteArray();
    }

    private static String fileNameOf(String s3Key) {
        int idx = s3Key.lastIndexOf('/');
        return idx == -1 ? s3Key : s3Key.substring(idx + 1);
    }

    private static String quoteOrNull(String value) {
        return value == null ? "null" : "\"" + escape(value) + "\"";
    }

    private static String escape(String value) {
        return value.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n");
    }

    private static final String README = """
            WellMade 액티브러닝용 신고 데이터 export
            ==========================================
            생성 시각: %s

            이 zip은 관리자가 "템플릿 후보"로 승인한 신고 건들의 원본 사진/영상과 manifest.json으로 구성됩니다.
            서버는 좌표 추출/DTW 템플릿 계산을 하지 않으므로(무거운 연산은 로컬에서 한다는 원칙),
            아래 순서로 로컬에서 직접 처리해주세요.

            1. 이 zip을 풀어서 로컬 mediapipe/opencv 환경(예: ai/ml_training/ 쪽 venv)에 둡니다.
            2. manifest.json의 각 항목(reasonCategory/aiJudgmentSnapshot)을 참고해 어떤 문제로
               신고된 사진/영상인지 확인합니다.
            3. 기존 prepare_posture_reference.py 패턴대로 좌표를 추출하고, 필요하면 DTW 템플릿을
               재계산합니다.
            4. 결과(숫자 배열/템플릿 JSON)를 사람이 검토한 뒤에만 레포에 반영합니다 — 신고 건을
               자동으로 템플릿에 편입시키지 않습니다(실촬영 데이터라는 점을 고려한 반자동 원칙).
            5. 처리를 마친 신고 건은 관리자 화면에서 별도로 표시해두면(예: 메모) 중복 처리를 막을 수
               있습니다 — 현재는 approved 상태가 그대로 유지되니 참고해주세요.
            """.formatted(java.time.LocalDateTime.now().format(DateTimeFormatter.ISO_LOCAL_DATE_TIME));
}

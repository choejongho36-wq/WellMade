import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getAdminDashboard } from '../lib/adminApi.js'
import './AdminPages.css'

export default function AdminDashboardPage() {
  const [stats, setStats] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getAdminDashboard().then(setStats).catch((err) => setError(err.message))
  }, [])

  return (
    <>
      <h1>대시보드</h1>
      {error && <p className="admin-error-text">{error}</p>}
      {stats && (
        <div className="admin-cards">
          <div className="admin-card">
            <div className="label">전체 회원</div>
            <div className="value">{stats.totalUsers}</div>
          </div>
          <div className="admin-card">
            <div className="label">오늘 신규가입</div>
            <div className="value">{stats.todaySignups}</div>
          </div>
          <div className="admin-card pending">
            <div className="label">검토 대기 신고</div>
            <div className="value">{stats.pendingReports}</div>
          </div>
          <div className="admin-card approved">
            <div className="label">승인된 신고</div>
            <div className="value">{stats.approvedReports}</div>
          </div>
          <div className="admin-card rejected">
            <div className="label">반려된 신고</div>
            <div className="value">{stats.rejectedReports}</div>
          </div>
        </div>
      )}

      <div className="admin-panel">
        <h2>신고 기반 액티브러닝 — 이 대시보드로 하는 일</h2>
        <p>
          사용자가 사진측정/세션리포트 화면에서 "이 판정이 이상해요"로 신고하면, 원본 사진·영상은
          S3에 저장되고 이 대시보드의 <Link to="/admin/reports">신고 관리</Link>에 쌓입니다.
          AI 판정 규칙(임계값·DTW 템플릿)을 실측 데이터로 계속 다듬어가는 것이 목적입니다.
        </p>
        <ol>
          <li><b>검토</b> — 신고 목록에서 항목을 열어 원본과 신고 당시 AI 판정 스냅샷을 확인합니다.</li>
          <li><b>승인 / 반려</b> — 템플릿 후보로 쓸 만하면 <b>승인</b>, 아니면 <b>반려</b>합니다.
            반려하면 원본은 S3에서 즉시 삭제됩니다(불필요한 촬영 데이터를 남기지 않기 위함).</li>
          <li><b>내보내기</b> — 승인된 건이 쌓이면 신고 관리 화면의 "승인된 항목 내보내기" 버튼으로
            zip을 받습니다. 여기엔 원본 파일과 manifest.json(신고 사유·판정 스냅샷),
            처리 안내가 담긴 README.txt가 함께 들어 있습니다.</li>
          <li><b>오프라인 처리</b> — 내려받은 zip을 로컬(mediapipe/opencv 설치된 개발 환경)에서
            기존 prepare_posture_reference.py 패턴으로 좌표 추출 → DTW 템플릿 재계산합니다.
            서버는 이 연산을 하지 않습니다.</li>
          <li><b>사람 검토 후 반영</b> — 재계산된 템플릿은 자동으로 서비스에 반영되지 않고, 사람이
            결과를 확인한 뒤에만 레포에 커밋합니다.</li>
        </ol>
      </div>
    </>
  )
}

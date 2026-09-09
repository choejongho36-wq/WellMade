import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { approveAdminReport, getAdminReportDetail, rejectAdminReport } from '../lib/adminApi.js'
import './AdminPages.css'

const SOURCE_TYPE_LABEL = { PHOTO: '사진측정', SESSION: '세션리포트' }
const REASON_LABEL = {
  FALSE_POSITIVE: '오탐 (정상인데 이상판정)',
  FALSE_NEGATIVE: '미탐 (이상인데 정상판정)',
  POSE_DETECTION_ERROR: '자세 인식 오류',
  OTHER: '기타',
}

function formatDateTime(iso) {
  if (!iso) return '-'
  return iso.replace('T', ' ').slice(0, 19)
}

export default function AdminReportDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [report, setReport] = useState(null)
  const [error, setError] = useState('')
  const [working, setWorking] = useState(false)

  const load = useCallback(() => {
    getAdminReportDetail(id).then(setReport).catch((err) => setError(err.message))
  }, [id])

  useEffect(() => { load() }, [load])

  const handleApprove = async () => {
    setWorking(true)
    try {
      await approveAdminReport(id)
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setWorking(false)
    }
  }

  const handleReject = async () => {
    if (!window.confirm('반려하면 원본 파일도 함께 삭제됩니다. 계속할까요?')) return
    setWorking(true)
    try {
      await rejectAdminReport(id)
      navigate('/admin/reports')
    } catch (err) {
      setError(err.message)
      setWorking(false)
    }
  }

  if (error && !report) return <p className="admin-error-text">{error}</p>
  if (!report) return <p>불러오는 중...</p>

  return (
    <>
      <h1>신고 #{report.id}</h1>
      {error && <p className="admin-error-text">{error}</p>}

      <div className="report-detail-grid">
        <div className="admin-panel report-detail-media">
          <h2>원본 (짧은 시간만 유효한 미리보기 링크)</h2>
          {report.sourceType === 'SESSION' ? (
            <video src={report.presignedUrl} controls />
          ) : (
            <img src={report.presignedUrl} alt="신고된 사진" />
          )}
          <p style={{ marginTop: 12 }}>
            <a href={report.presignedUrl} target="_blank" rel="noreferrer">새 탭에서 원본 열기</a>
          </p>
        </div>

        <div className="admin-panel">
          <h2>신고 정보</h2>
          <div className="report-detail-field">
            <span className="k">상태</span>
            <span className={`badge badge-${report.status.toLowerCase()}`}>{report.status}</span>
          </div>
          <div className="report-detail-field">
            <span className="k">구분</span>
            <span>{SOURCE_TYPE_LABEL[report.sourceType] ?? report.sourceType}</span>
          </div>
          <div className="report-detail-field">
            <span className="k">사유</span>
            <span>{REASON_LABEL[report.reasonCategory] ?? report.reasonCategory}</span>
          </div>
          {report.reasonDetail && (
            <div className="report-detail-field">
              <span className="k">기타 사유 내용</span>
              <span>{report.reasonDetail}</span>
            </div>
          )}
          <div className="report-detail-field">
            <span className="k">신고 시각</span>
            <span>{formatDateTime(report.createdAt)}</span>
          </div>
          {report.reviewedAt && (
            <div className="report-detail-field">
              <span className="k">검토</span>
              <span>{report.reviewedBy} / {formatDateTime(report.reviewedAt)}</span>
            </div>
          )}

          <div className="report-detail-field">
            <span className="k">신고 당시 AI 판정 스냅샷</span>
            <pre className="judgment-snapshot">{report.aiJudgmentSnapshot ?? '(전달된 값 없음)'}</pre>
          </div>

          {report.status === 'PENDING' && (
            <div style={{ marginTop: 20, display: 'flex', gap: 8 }}>
              <button type="button" className="admin-btn admin-btn-primary" onClick={handleApprove} disabled={working}>
                템플릿 후보로 승인
              </button>
              <button type="button" className="admin-btn admin-btn-danger" onClick={handleReject} disabled={working}>
                반려 (원본 삭제)
              </button>
            </div>
          )}
        </div>
      </div>
    </>
  )
}

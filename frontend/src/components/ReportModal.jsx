/**
 * "이 판정이 이상해요" 신고 모달 — 사진측정(PhotoCoachingPage) 결과 패널과 세션리포트
 * (SquatCoachingPage ReportView)에서 공용으로 쓴다.
 *
 * 공용 Modal.jsx를 그대로 쓰고(ExerciseGuideModal과 동일 패턴), 사유 3개 중 하나를 고르게
 * 하고 "기타"를 고르면 직접 입력 textarea가 열린다. 제출은 부모가 넘겨준 getReportPayload()
 * (원본 파일 Blob + 파일명 + judgmentSnapshot을 만들어주는 함수)의 결과를 그대로
 * useAuth().submitReport로 보낸다 — 원본을 어떻게 만드는지는 페이지마다 다르므로
 * (사진측정은 업로드된 이미지, 세션리포트는 렙별 좌표 시계열 JSON) 이 모달은 모른다.
 */
import { useState } from 'react'
import Modal from './Modal.jsx'
import './ReportModal.css'

export const REPORT_REASONS = [
  { value: 'FALSE_POSITIVE', label: '정상인데 이상하다고 판정했어요' },
  { value: 'FALSE_NEGATIVE', label: '이상한데 정상으로 판정했어요' },
  { value: 'OTHER', label: '기타' },
]

function ReportModal({ onClose, onSubmit }) {
  const [reasonCategory, setReasonCategory] = useState('FALSE_POSITIVE')
  const [reasonDetail, setReasonDetail] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (reasonCategory === 'OTHER' && !reasonDetail.trim()) {
      setError('기타 사유를 입력해주세요')
      return
    }
    setSubmitting(true)
    setError('')
    try {
      await onSubmit({ reasonCategory, reasonDetail: reasonCategory === 'OTHER' ? reasonDetail.trim() : '' })
      setDone(true)
    } catch (err) {
      setError(err.message || '신고에 실패했어요. 잠시 후 다시 시도해주세요')
    } finally {
      setSubmitting(false)
    }
  }

  if (done) {
    return (
      <Modal onClose={onClose} className="report-modal report-modal-done-state">
        <div className="report-modal-done">
          <div className="report-modal-done-icon">✓</div>
          <h2>신고가 접수됐어요</h2>
          <p>관리자가 검토해 AI 판정 개선에 참고할게요. 알려주셔서 감사합니다.</p>
          <button type="button" className="squat-btn squat-btn-primary" onClick={onClose}>확인</button>
        </div>
      </Modal>
    )
  }

  return (
    <Modal onClose={onClose} className="report-modal">
      <h2 className="modal-title">이 판정, 이상한가요?</h2>
      <p className="modal-sub">신고해주신 사진/영상은 AI 판정을 더 정확하게 다듬는 데 참고 자료로 쓰여요.</p>

      <form onSubmit={handleSubmit}>
        <div className="report-modal-reasons">
          {REPORT_REASONS.map((r) => (
            <label key={r.value} className={`report-reason-option${reasonCategory === r.value ? ' selected' : ''}`}>
              <input
                type="radio"
                name="reasonCategory"
                value={r.value}
                checked={reasonCategory === r.value}
                onChange={() => setReasonCategory(r.value)}
              />
              {r.label}
            </label>
          ))}
        </div>

        {reasonCategory === 'OTHER' && (
          <textarea
            className="report-modal-textarea"
            placeholder="어떤 점이 이상했는지 적어주세요"
            value={reasonDetail}
            onChange={(e) => setReasonDetail(e.target.value)}
            rows={3}
          />
        )}

        {error && <p className="squat-error">{error}</p>}

        <div className="report-modal-actions">
          <button type="button" className="squat-btn squat-btn-outline" onClick={onClose} disabled={submitting}>
            취소
          </button>
          <button type="submit" className="squat-btn squat-btn-primary" disabled={submitting}>
            {submitting ? '전송 중...' : '신고하기'}
          </button>
        </div>
      </form>
    </Modal>
  )
}

export default ReportModal

/**
 * "이 판정이 이상해요" 신고 버튼이 여는 모달 — 사진측정(PhotoCoachingPage)과 세션리포트
 * (SquatCoachingPage)에서 공용으로 쓴다.
 */
import Modal from './Modal.jsx'
import './ReportModal.css'

function ReportModal({ onClose }) {
  return (
    <Modal onClose={onClose} className="report-modal report-modal-done-state">
      <div className="report-modal-done">
        <h2>추후 제공될 기능이에요</h2>
        <p>신고 기능은 아직 준비 중이에요. 조금만 기다려 주세요.</p>
        <button type="button" className="squat-btn squat-btn-primary" onClick={onClose}>확인</button>
      </div>
    </Modal>
  )
}

export default ReportModal

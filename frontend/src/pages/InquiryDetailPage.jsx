import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import PageShell from '../components/PageShell.jsx'
import { useAuth } from '../lib/auth.js'
import './SupportPages.css'

const CATEGORY_LABEL = { BUG: '버그', REPORT: '신고', INQUIRY: '문의', SUGGESTION: '제안' }

function formatDate(iso) {
  if (!iso) return '-'
  return iso.slice(0, 10)
}

export default function InquiryDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { getInquiry, deleteInquiry } = useAuth()
  const [inquiry, setInquiry] = useState(null)
  const [error, setError] = useState('')
  const [deleting, setDeleting] = useState(false)

  const load = useCallback(() => {
    getInquiry(id).then(setInquiry).catch((err) => setError(err.message))
  }, [id, getInquiry])

  useEffect(() => { load() }, [load])

  const handleDelete = async () => {
    if (!window.confirm('문의를 삭제할까요?')) return
    setDeleting(true)
    try {
      await deleteInquiry(id)
      navigate('/inquiry')
    } catch (err) {
      setError(err.message)
      setDeleting(false)
    }
  }

  if (error && !inquiry) return <PageShell><div className="support-page"><p className="support-error">{error}</p></div></PageShell>
  if (!inquiry) return <PageShell><div className="support-page"><p className="support-empty">불러오는 중...</p></div></PageShell>

  return (
    <PageShell>
      <div className="support-page">
        <Link to="/inquiry" className="support-eyebrow">← 1:1 INQUIRY</Link>
        <div className="support-detail">
          <span className={`support-badge ${inquiry.status === 'ANSWERED' ? 'support-badge-answered' : 'support-badge-pending'}`}>
            {inquiry.status === 'ANSWERED' ? '답변완료' : '답변대기'}
          </span>
          <h1 className="support-detail-title">{inquiry.secret ? '🔒 ' : ''}{inquiry.title}</h1>
          <div className="support-detail-meta">
            <span>{CATEGORY_LABEL[inquiry.category] ?? inquiry.category}</span>
            <span>{formatDate(inquiry.createdAt)}</span>
          </div>

          {inquiry.hidden ? (
            <p className="support-detail-content">비밀글입니다. 작성자와 관리자만 볼 수 있어요.</p>
          ) : (
            <>
              <div className="support-detail-content">{inquiry.content}</div>

              {inquiry.status === 'ANSWERED' ? (
                <div className="support-answer-box">
                  <div className="label">관리자 답변</div>
                  <p>{inquiry.answer}</p>
                </div>
              ) : (
                <div className="support-answer-box">
                  <div className="label">답변 대기중</div>
                  <p>확인 후 순차적으로 답변해드릴게요.</p>
                </div>
              )}
            </>
          )}

          {error && <p className="support-error">{error}</p>}

          {inquiry.mine && (
            <div className="support-detail-actions">
              <button type="button" className="support-btn support-btn-outline" onClick={() => navigate(`/inquiry/${id}/edit`)}>
                수정
              </button>
              <button type="button" className="support-btn support-btn-danger" onClick={handleDelete} disabled={deleting}>
                삭제
              </button>
            </div>
          )}
        </div>
      </div>
    </PageShell>
  )
}

import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { answerAdminInquiry, deleteAdminInquiry, deleteAdminInquiryAnswer, getAdminInquiryDetail } from '../lib/adminApi.js'
import './AdminPages.css'

const CATEGORY_LABEL = { BUG: '버그', REPORT: '신고', INQUIRY: '문의', SUGGESTION: '제안' }

function formatDateTime(iso) {
  if (!iso) return '-'
  return iso.replace('T', ' ').slice(0, 19)
}

export default function AdminInquiryDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [inquiry, setInquiry] = useState(null)
  const [answerText, setAnswerText] = useState('')
  const [error, setError] = useState('')
  const [working, setWorking] = useState(false)

  const load = useCallback(() => {
    getAdminInquiryDetail(id)
      .then((data) => {
        setInquiry(data)
        setAnswerText(data.answer ?? '')
      })
      .catch((err) => setError(err.message))
  }, [id])

  useEffect(() => { load() }, [load])

  const handleAnswer = async (e) => {
    e.preventDefault()
    if (!answerText.trim()) return
    setWorking(true)
    try {
      await answerAdminInquiry(id, answerText)
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setWorking(false)
    }
  }

  const handleDeleteAnswer = async () => {
    if (!window.confirm('등록된 답변을 삭제할까요? (문의는 다시 답변대기 상태가 됩니다)')) return
    setWorking(true)
    try {
      await deleteAdminInquiryAnswer(id)
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setWorking(false)
    }
  }

  const handleDeleteInquiry = async () => {
    if (!window.confirm('문의를 완전히 삭제할까요?')) return
    setWorking(true)
    try {
      await deleteAdminInquiry(id)
      navigate('/admin/inquiries')
    } catch (err) {
      setError(err.message)
      setWorking(false)
    }
  }

  if (error && !inquiry) return <p className="admin-error-text">{error}</p>
  if (!inquiry) return <p>불러오는 중...</p>

  return (
    <>
      <h1>문의 #{inquiry.id}</h1>
      {error && <p className="admin-error-text">{error}</p>}

      <div className="admin-panel">
        <div className="report-detail-field">
          <span className="k">상태</span>
          <span className={`badge badge-${inquiry.status.toLowerCase()}`}>{inquiry.status}</span>
        </div>
        <div className="report-detail-field">
          <span className="k">분류</span>
          <span>{CATEGORY_LABEL[inquiry.category] ?? inquiry.category}</span>
        </div>
        <div className="report-detail-field">
          <span className="k">작성자</span>
          <span>{inquiry.authorEmail}{inquiry.secret ? ' (비밀글)' : ''}</span>
        </div>
        <div className="report-detail-field">
          <span className="k">제목</span>
          <span>{inquiry.title}</span>
        </div>
        <div className="report-detail-field">
          <span className="k">내용</span>
          <span style={{ whiteSpace: 'pre-wrap' }}>{inquiry.content}</span>
        </div>
        <div className="report-detail-field">
          <span className="k">작성 시각</span>
          <span>{formatDateTime(inquiry.createdAt)}</span>
        </div>

        <form onSubmit={handleAnswer} style={{ marginTop: 20 }}>
          <label style={{ display: 'block', fontSize: 13.5, fontWeight: 600, marginBottom: 6 }}>답변</label>
          <textarea
            value={answerText}
            onChange={(e) => setAnswerText(e.target.value)}
            style={{ width: '100%', minHeight: 140, padding: 10, borderRadius: 8, border: '1px solid #d1d5db', fontFamily: 'inherit', fontSize: 14 }}
          />
          <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
            <button type="submit" className="admin-btn admin-btn-primary" disabled={working}>
              {inquiry.status === 'ANSWERED' ? '답변 수정' : '답변 등록'}
            </button>
            {inquiry.status === 'ANSWERED' && (
              <button type="button" className="admin-btn admin-btn-outline" onClick={handleDeleteAnswer} disabled={working}>
                답변 삭제
              </button>
            )}
            <button type="button" className="admin-btn admin-btn-danger" onClick={handleDeleteInquiry} disabled={working} style={{ marginLeft: 'auto' }}>
              문의 삭제
            </button>
          </div>
        </form>
      </div>
    </>
  )
}

import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import PageShell from '../components/PageShell.jsx'
import { useAuth } from '../lib/auth.js'
import './SupportPages.css'

const CATEGORY_LABEL = { BUG: '버그', REPORT: '신고', INQUIRY: '문의', SUGGESTION: '제안' }

function formatDate(iso) {
  if (!iso) return '-'
  return iso.slice(0, 10)
}

export default function InquiryPage() {
  const { getInquiries } = useAuth()
  const navigate = useNavigate()
  const [inquiries, setInquiries] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getInquiries().then(setInquiries).catch((err) => setError(err.message))
  }, [getInquiries])

  return (
    <PageShell>
      <div className="support-page">
        <div className="support-section-header">
          <div>
            <p className="support-eyebrow">1:1 INQUIRY</p>
            <h1 className="support-title">1:1 문의</h1>
            <p className="support-hint">궁금한 점을 남겨주시면 확인 후 답변해드려요.</p>
          </div>
          <button type="button" className="support-btn" onClick={() => navigate('/inquiry/new')}>
            문의하기
          </button>
        </div>

        {error && <p className="support-error">{error}</p>}

        {inquiries && inquiries.length === 0 && <p className="support-empty">등록된 문의가 없습니다.</p>}

        {inquiries && inquiries.length > 0 && (
          <div className="support-list">
            {inquiries.map((q) => (
              <button
                type="button"
                key={q.id}
                className="support-row"
                onClick={() => navigate(`/inquiry/${q.id}`)}
              >
                <span className="support-row-category">{CATEGORY_LABEL[q.category] ?? q.category}</span>
                <span className="support-row-title">{q.secret ? '🔒 ' : ''}{q.title}</span>
                <span className={`support-badge ${q.status === 'ANSWERED' ? 'support-badge-answered' : 'support-badge-pending'}`}>
                  {q.status === 'ANSWERED' ? '답변완료' : '답변대기'}
                </span>
                <span className="support-row-meta">{formatDate(q.createdAt)}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </PageShell>
  )
}

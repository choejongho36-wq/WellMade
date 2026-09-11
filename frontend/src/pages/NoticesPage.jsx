import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import PageShell from '../components/PageShell.jsx'
import { useAuth } from '../lib/auth.js'
import './SupportPages.css'

function formatDate(iso) {
  if (!iso) return '-'
  return iso.slice(0, 10)
}

export default function NoticesPage() {
  const { getNotices } = useAuth()
  const navigate = useNavigate()
  const [notices, setNotices] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getNotices().then(setNotices).catch((err) => setError(err.message))
  }, [getNotices])

  return (
    <PageShell>
      <div className="support-page">
        <p className="support-eyebrow">NOTICE</p>
        <h1 className="support-title">공지사항</h1>
        <p className="support-hint">서비스 업데이트와 안내 사항을 알려드려요.</p>

        {error && <p className="support-error">{error}</p>}

        {notices && notices.length === 0 && <p className="support-empty">등록된 공지사항이 없습니다.</p>}

        {notices && notices.length > 0 && (
          <div className="support-list">
            {notices.map((n) => (
              <button
                type="button"
                key={n.id}
                className="support-row"
                onClick={() => navigate(`/notices/${n.id}`)}
              >
                <span className="support-row-badge-slot">
                  {n.pinned && <span className="support-badge support-badge-pinned">고정</span>}
                </span>
                <span className="support-row-title">{n.title}</span>
                <span className="support-row-meta">{formatDate(n.createdAt)}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </PageShell>
  )
}

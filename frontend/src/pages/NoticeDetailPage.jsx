import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import PageShell from '../components/PageShell.jsx'
import { useAuth } from '../lib/auth.js'
import './SupportPages.css'

function formatDate(iso) {
  if (!iso) return '-'
  return iso.slice(0, 10)
}

export default function NoticeDetailPage() {
  const { id } = useParams()
  const { getNotice } = useAuth()
  const [notice, setNotice] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getNotice(id).then(setNotice).catch((err) => setError(err.message))
  }, [id, getNotice])

  if (error) return <PageShell><div className="support-page"><p className="support-error">{error}</p></div></PageShell>
  if (!notice) return <PageShell><div className="support-page"><p className="support-empty">불러오는 중...</p></div></PageShell>

  return (
    <PageShell>
      <div className="support-page">
        <Link to="/notices" className="support-eyebrow">← NOTICE</Link>
        <div className="support-detail">
          {notice.pinned && <span className="support-badge support-badge-pinned">고정</span>}
          <h1 className="support-detail-title">{notice.title}</h1>
          <div className="support-detail-meta">
            <span>{formatDate(notice.createdAt)}</span>
          </div>
          <div className="support-detail-content">{notice.content}</div>
        </div>
      </div>
    </PageShell>
  )
}

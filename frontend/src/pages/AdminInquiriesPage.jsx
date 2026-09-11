import { useCallback, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { getAdminInquiries } from '../lib/adminApi.js'
import './AdminPages.css'

const STATUS_TABS = [
  { value: '', label: '전체' },
  { value: 'PENDING', label: '답변대기' },
  { value: 'ANSWERED', label: '답변완료' },
]

const CATEGORY_LABEL = { BUG: '버그', REPORT: '신고', INQUIRY: '문의', SUGGESTION: '제안' }

function formatDateTime(iso) {
  if (!iso) return '-'
  return iso.replace('T', ' ').slice(0, 16)
}

export default function AdminInquiriesPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const status = searchParams.get('status') ?? ''
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    getAdminInquiries(status || undefined, 0)
      .then(setData)
      .catch((err) => setError(err.message))
  }, [status])

  useEffect(() => { load() }, [load])

  return (
    <>
      <h1>1:1 문의 관리</h1>

      <div className="admin-tabs">
        {STATUS_TABS.map((tab) => (
          <button
            key={tab.value}
            type="button"
            className={`admin-tab${status === tab.value ? ' active' : ''}`}
            onClick={() => setSearchParams(tab.value ? { status: tab.value } : {})}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {error && <p className="admin-error-text">{error}</p>}

      <div className="admin-panel">
        <table className="admin-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>분류</th>
              <th>제목</th>
              <th>상태</th>
              <th>작성일</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {data?.content.map((q) => (
              <tr key={q.id}>
                <td>{q.id}</td>
                <td>{CATEGORY_LABEL[q.category] ?? q.category}</td>
                <td>{q.secret ? '🔒 ' : ''}{q.title}</td>
                <td>
                  <span className={`badge badge-${q.status.toLowerCase()}`}>{q.status}</span>
                </td>
                <td>{formatDateTime(q.createdAt)}</td>
                <td><Link className="admin-btn admin-btn-outline" to={`/admin/inquiries/${q.id}`}>보기</Link></td>
              </tr>
            ))}
            {data && data.content.length === 0 && (
              <tr>
                <td colSpan={6} style={{ textAlign: 'center', color: '#9ca3af', padding: '24px 0' }}>
                  문의 내역이 없습니다.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  )
}

import { useCallback, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ADMIN_REPORT_EXPORT_URL, getAdminReports } from '../lib/adminApi.js'
import './AdminPages.css'

const STATUS_TABS = [
  { value: '', label: '전체' },
  { value: 'PENDING', label: '대기' },
  { value: 'APPROVED', label: '승인' },
  { value: 'REJECTED', label: '반려' },
]

const SOURCE_TYPE_LABEL = { PHOTO: '사진측정', SESSION: '세션리포트' }
const REASON_LABEL = {
  FALSE_POSITIVE: '오탐 (정상인데 이상판정)',
  FALSE_NEGATIVE: '미탐 (이상인데 정상판정)',
  POSE_DETECTION_ERROR: '자세 인식 오류',
}

function reasonText(r) {
  return REASON_LABEL[r.reasonCategory] ?? `기타: ${r.reasonDetail ?? ''}`
}

function formatDateTime(iso) {
  if (!iso) return '-'
  return iso.replace('T', ' ').slice(0, 16)
}

export default function AdminReportsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const status = searchParams.get('status') ?? ''
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    getAdminReports(status || undefined, 0)
      .then(setData)
      .catch((err) => setError(err.message))
  }, [status])

  useEffect(() => { load() }, [load])

  return (
    <>
      <h1>신고 관리</h1>

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
        <a className="admin-btn admin-btn-outline" style={{ marginLeft: 'auto' }} href={ADMIN_REPORT_EXPORT_URL}>
          승인된 항목 내보내기 (zip)
        </a>
      </div>

      {error && <p className="admin-error-text">{error}</p>}

      <div className="admin-panel">
        <table className="admin-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>구분</th>
              <th>사유</th>
              <th>상태</th>
              <th>신고 시각</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {data?.content.map((r) => (
              <tr key={r.id}>
                <td>{r.id}</td>
                <td>{SOURCE_TYPE_LABEL[r.sourceType] ?? r.sourceType}</td>
                <td>{reasonText(r)}</td>
                <td>
                  <span className={`badge badge-${r.status.toLowerCase()}`}>{r.status}</span>
                </td>
                <td>{formatDateTime(r.createdAt)}</td>
                <td><Link className="admin-btn admin-btn-outline" to={`/admin/reports/${r.id}`}>보기</Link></td>
              </tr>
            ))}
            {data && data.content.length === 0 && (
              <tr>
                <td colSpan={6} style={{ textAlign: 'center', color: '#9ca3af', padding: '24px 0' }}>
                  신고 내역이 없습니다.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  )
}

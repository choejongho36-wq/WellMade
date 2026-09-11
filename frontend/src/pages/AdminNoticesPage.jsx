import { useCallback, useEffect, useState } from 'react'
import { createAdminNotice, deleteAdminNotice, getAdminNotices, updateAdminNotice } from '../lib/adminApi.js'
import './AdminPages.css'

const EMPTY_FORM = { title: '', content: '', pinned: false }

function formatDateTime(iso) {
  if (!iso) return '-'
  return iso.replace('T', ' ').slice(0, 16)
}

export default function AdminNoticesPage() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [editingId, setEditingId] = useState(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [saving, setSaving] = useState(false)

  const load = useCallback(() => {
    getAdminNotices(0).then(setData).catch((err) => setError(err.message))
  }, [])

  useEffect(() => { load() }, [load])

  const startCreate = () => {
    setEditingId('new')
    setForm(EMPTY_FORM)
  }

  const startEdit = (notice) => {
    setEditingId(notice.id)
    setForm({ title: notice.title, content: notice.content, pinned: notice.pinned })
  }

  const cancelEdit = () => {
    setEditingId(null)
    setForm(EMPTY_FORM)
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setSaving(true)
    setError('')
    try {
      if (editingId === 'new') {
        await createAdminNotice(form)
      } else {
        await updateAdminNotice(editingId, form)
      }
      cancelEdit()
      load()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id) => {
    if (!window.confirm('공지사항을 삭제할까요?')) return
    try {
      await deleteAdminNotice(id)
      load()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <>
      <h1>공지사항 관리</h1>
      {error && <p className="admin-error-text">{error}</p>}

      {editingId ? (
        <div className="admin-panel">
          <form onSubmit={handleSubmit}>
            <label style={{ display: 'block', fontSize: 13.5, fontWeight: 600, marginBottom: 6 }}>제목</label>
            <input
              type="text"
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              style={{ width: '100%', padding: 10, borderRadius: 8, border: '1px solid #d1d5db', marginBottom: 12 }}
            />
            <label style={{ display: 'block', fontSize: 13.5, fontWeight: 600, marginBottom: 6 }}>내용</label>
            <textarea
              value={form.content}
              onChange={(e) => setForm({ ...form, content: e.target.value })}
              style={{ width: '100%', minHeight: 160, padding: 10, borderRadius: 8, border: '1px solid #d1d5db', fontFamily: 'inherit', fontSize: 14, marginBottom: 12 }}
            />
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13.5, fontWeight: 600, marginBottom: 12 }}>
              <input type="checkbox" checked={form.pinned} onChange={(e) => setForm({ ...form, pinned: e.target.checked })} />
              상단 고정
            </label>
            <div style={{ display: 'flex', gap: 8 }}>
              <button type="submit" className="admin-btn admin-btn-primary" disabled={saving}>저장</button>
              <button type="button" className="admin-btn admin-btn-outline" onClick={cancelEdit}>취소</button>
            </div>
          </form>
        </div>
      ) : (
        <button type="button" className="admin-btn admin-btn-primary" onClick={startCreate} style={{ marginBottom: 16 }}>
          공지사항 작성
        </button>
      )}

      <div className="admin-panel">
        <table className="admin-table">
          <thead>
            <tr>
              <th></th>
              <th>제목</th>
              <th>작성일</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {data?.content.map((notice) => (
              <tr key={notice.id}>
                <td>{notice.pinned && <span className="badge badge-pending">고정</span>}</td>
                <td>{notice.title}</td>
                <td>{formatDateTime(notice.createdAt)}</td>
                <td style={{ display: 'flex', gap: 8 }}>
                  <button type="button" className="admin-btn admin-btn-outline" onClick={() => startEdit(notice)}>수정</button>
                  <button type="button" className="admin-btn admin-btn-danger" onClick={() => handleDelete(notice.id)}>삭제</button>
                </td>
              </tr>
            ))}
            {data && data.content.length === 0 && (
              <tr>
                <td colSpan={4} style={{ textAlign: 'center', color: '#9ca3af', padding: '24px 0' }}>
                  등록된 공지사항이 없습니다.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  )
}

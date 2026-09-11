import { useCallback, useEffect, useState } from 'react'
import { createAdminFaq, deleteAdminFaq, getAdminFaqs, updateAdminFaq } from '../lib/adminApi.js'
import './AdminPages.css'

const EMPTY_FORM = { question: '', answer: '', displayOrder: 0 }

export default function AdminFaqsPage() {
  const [faqs, setFaqs] = useState(null)
  const [error, setError] = useState('')
  const [editingId, setEditingId] = useState(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [saving, setSaving] = useState(false)

  const load = useCallback(() => {
    getAdminFaqs().then(setFaqs).catch((err) => setError(err.message))
  }, [])

  useEffect(() => { load() }, [load])

  const startCreate = () => {
    setEditingId('new')
    setForm(EMPTY_FORM)
  }

  const startEdit = (faq) => {
    setEditingId(faq.id)
    setForm({ question: faq.question, answer: faq.answer, displayOrder: faq.displayOrder })
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
      const payload = { ...form, displayOrder: Number(form.displayOrder) || 0 }
      if (editingId === 'new') {
        await createAdminFaq(payload)
      } else {
        await updateAdminFaq(editingId, payload)
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
    if (!window.confirm('FAQ를 삭제할까요?')) return
    try {
      await deleteAdminFaq(id)
      load()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <>
      <h1>FAQ 관리</h1>
      {error && <p className="admin-error-text">{error}</p>}

      {editingId ? (
        <div className="admin-panel">
          <form onSubmit={handleSubmit}>
            <label style={{ display: 'block', fontSize: 13.5, fontWeight: 600, marginBottom: 6 }}>질문</label>
            <input
              type="text"
              value={form.question}
              onChange={(e) => setForm({ ...form, question: e.target.value })}
              style={{ width: '100%', padding: 10, borderRadius: 8, border: '1px solid #d1d5db', marginBottom: 12 }}
            />
            <label style={{ display: 'block', fontSize: 13.5, fontWeight: 600, marginBottom: 6 }}>답변</label>
            <textarea
              value={form.answer}
              onChange={(e) => setForm({ ...form, answer: e.target.value })}
              style={{ width: '100%', minHeight: 120, padding: 10, borderRadius: 8, border: '1px solid #d1d5db', fontFamily: 'inherit', fontSize: 14, marginBottom: 12 }}
            />
            <label style={{ display: 'block', fontSize: 13.5, fontWeight: 600, marginBottom: 6 }}>노출 순서 (작을수록 위)</label>
            <input
              type="number"
              value={form.displayOrder}
              onChange={(e) => setForm({ ...form, displayOrder: e.target.value })}
              style={{ width: 120, padding: 10, borderRadius: 8, border: '1px solid #d1d5db', marginBottom: 12 }}
            />
            <div style={{ display: 'flex', gap: 8 }}>
              <button type="submit" className="admin-btn admin-btn-primary" disabled={saving}>저장</button>
              <button type="button" className="admin-btn admin-btn-outline" onClick={cancelEdit}>취소</button>
            </div>
          </form>
        </div>
      ) : (
        <button type="button" className="admin-btn admin-btn-primary" onClick={startCreate} style={{ marginBottom: 16 }}>
          FAQ 추가
        </button>
      )}

      <div className="admin-panel">
        <table className="admin-table">
          <thead>
            <tr>
              <th>순서</th>
              <th>질문</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {faqs?.map((faq) => (
              <tr key={faq.id}>
                <td>{faq.displayOrder}</td>
                <td>{faq.question}</td>
                <td style={{ display: 'flex', gap: 8 }}>
                  <button type="button" className="admin-btn admin-btn-outline" onClick={() => startEdit(faq)}>수정</button>
                  <button type="button" className="admin-btn admin-btn-danger" onClick={() => handleDelete(faq.id)}>삭제</button>
                </td>
              </tr>
            ))}
            {faqs && faqs.length === 0 && (
              <tr>
                <td colSpan={3} style={{ textAlign: 'center', color: '#9ca3af', padding: '24px 0' }}>
                  등록된 FAQ가 없습니다.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  )
}

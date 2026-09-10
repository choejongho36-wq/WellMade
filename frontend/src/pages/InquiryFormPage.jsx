import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import PageShell from '../components/PageShell.jsx'
import { useAuth } from '../lib/auth.js'
import './SupportPages.css'

const CATEGORY_OPTIONS = [
  { value: 'INQUIRY', label: '문의' },
  { value: 'BUG', label: '버그' },
  { value: 'REPORT', label: '신고' },
  { value: 'SUGGESTION', label: '제안' },
]

// 새 문의 작성(/inquiry/new)과 내 글 수정(/inquiry/:id/edit)을 한 컴포넌트에서 처리한다 -
// id가 있으면 기존 글을 불러와 채워두고 저장 시 updateInquiry, 없으면 createInquiry.
export default function InquiryFormPage() {
  const { id } = useParams()
  const isEdit = Boolean(id)
  const navigate = useNavigate()
  const { getInquiry, createInquiry, updateInquiry } = useAuth()

  const [title, setTitle] = useState('')
  const [category, setCategory] = useState('INQUIRY')
  const [content, setContent] = useState('')
  const [secret, setSecret] = useState(false)
  const [loading, setLoading] = useState(isEdit)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!isEdit) return
    getInquiry(id)
      .then((q) => {
        setTitle(q.title)
        setCategory(q.category)
        setContent(q.content ?? '')
        setSecret(q.secret)
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [id, isEdit, getInquiry])

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!title.trim() || !content.trim()) {
      setError('제목과 내용을 입력해주세요.')
      return
    }
    setSaving(true)
    setError('')
    try {
      const payload = { title, category, content, secret }
      const saved = isEdit ? await updateInquiry(id, payload) : await createInquiry(payload)
      navigate(`/inquiry/${saved.id}`)
    } catch (err) {
      setError(err.message)
      setSaving(false)
    }
  }

  if (loading) return <PageShell><div className="support-page"><p className="support-empty">불러오는 중...</p></div></PageShell>

  return (
    <PageShell>
      <div className="support-page">
        <p className="support-eyebrow">1:1 INQUIRY</p>
        <h1 className="support-title">{isEdit ? '문의 수정' : '문의하기'}</h1>

        {error && <p className="support-error">{error}</p>}

        <form className="support-form" onSubmit={handleSubmit}>
          <label>
            분류
            <select value={category} onChange={(e) => setCategory(e.target.value)}>
              {CATEGORY_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </label>

          <label>
            제목
            <input type="text" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={100} />
          </label>

          <label>
            내용
            <textarea value={content} onChange={(e) => setContent(e.target.value)} />
          </label>

          <label className="support-form-checkbox">
            <input type="checkbox" checked={secret} onChange={(e) => setSecret(e.target.checked)} />
            비밀글로 등록 (본인과 관리자만 내용을 볼 수 있어요)
          </label>

          <div className="support-form-actions">
            <button type="submit" className="support-btn" disabled={saving}>
              {saving ? '저장 중...' : '등록'}
            </button>
            <button type="button" className="support-btn support-btn-outline" onClick={() => navigate(-1)}>
              취소
            </button>
          </div>
        </form>
      </div>
    </PageShell>
  )
}

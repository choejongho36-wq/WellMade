import { useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { useAdminAuth } from '../lib/adminAuth.js'
import './AdminLoginPage.css'

export default function AdminLoginPage() {
  const { admin, error, login } = useAdminAuth()
  const [loginId, setLoginId] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [localError, setLocalError] = useState('')

  useEffect(() => { setLocalError(error) }, [error])

  if (admin) return <Navigate to="/admin" replace />

  const handleSubmit = async (e) => {
    e.preventDefault()
    setSubmitting(true)
    setLocalError('')
    const ok = await login(loginId, password)
    setSubmitting(false)
    if (!ok) setLocalError(error || '로그인에 실패했습니다')
  }

  return (
    <div className="admin-login-shell">
      <div className="admin-login-wrap">
        <div className="admin-login-box">
          <h1 className="admin-login-title">WellMade<span>Admin</span></h1>
          <p className="admin-login-subtitle">운영 대시보드에 로그인하세요</p>
          {localError && <div className="admin-login-error">{localError}</div>}
          <form onSubmit={handleSubmit}>
            <input
              type="text" placeholder="아이디" autoComplete="username" required
              value={loginId} onChange={(e) => setLoginId(e.target.value)}
            />
            <input
              type="password" placeholder="비밀번호" autoComplete="current-password" required
              value={password} onChange={(e) => setPassword(e.target.value)}
            />
            <button type="submit" className="admin-login-btn" disabled={submitting}>
              {submitting ? '로그인 중...' : '로그인'}
            </button>
          </form>
        </div>
        <p className="admin-login-footer">&copy; WellMade</p>
      </div>
    </div>
  )
}

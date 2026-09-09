/**
 * 관리자 로그인 상태 컨텍스트. 일반 회원 쪽 useAuth()(auth.js)와 별개 — 관리자 토큰은
 * httpOnly 쿠키에만 있어 프론트가 값을 직접 들고 있을 수 없으므로, "로그인됐는지"는
 * 항상 서버(/api/admin/auth/me)에 물어봐서 확인한다.
 */
import { createContext, createElement, useCallback, useContext, useEffect, useState } from 'react'
import { adminLogin, adminLogout, adminMe } from './adminApi.js'

const AdminAuthContext = createContext(null)

export function AdminAuthProvider({ children }) {
  return createElement(AdminAuthContext.Provider, { value: useAdminAuthState() }, children)
}

export function useAdminAuth() {
  return useContext(AdminAuthContext)
}

function useAdminAuthState() {
  // undefined = 아직 서버에 확인 중, null = 비로그인, { loginId } = 로그인됨
  const [admin, setAdmin] = useState(undefined)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    adminMe()
      .then((data) => { if (!cancelled) setAdmin(data) })
      .catch(() => { if (!cancelled) setAdmin(null) })
    return () => { cancelled = true }
  }, [])

  const login = useCallback(async (loginId, password) => {
    setError('')
    try {
      const data = await adminLogin(loginId, password)
      setAdmin(data)
      return true
    } catch (err) {
      setError(err.message)
      return false
    }
  }, [])

  const logout = useCallback(async () => {
    await adminLogout()
    setAdmin(null)
  }, [])

  return { admin, error, login, logout }
}

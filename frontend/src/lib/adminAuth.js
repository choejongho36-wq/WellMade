/**
 * 관리자 로그인 상태 컨텍스트. 일반 회원 쪽 useAuth()(auth.js)와 별개 — 관리자 토큰은
 * httpOnly 쿠키에만 있어 프론트가 값을 직접 들고 있을 수 없으므로, "로그인됐는지"는
 * 항상 서버(/api/admin/auth/me)에 물어봐서 확인한다.
 */
import { createContext, createElement, useCallback, useContext, useEffect, useRef, useState } from 'react'
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

  // 탭이 백그라운드로 전환되는 순간(다른 탭/창으로 이동, 최소화 등) 자동 로그아웃한다 —
  // 관리자 화면이 자리를 비운 사이 남의 눈에 그대로 노출되지 않게 하기 위함. admin이 이미
  // null/undefined면(로그인 안 됐거나 확인 중) 부를 필요 없다.
  const adminRef = useRef(admin)
  useEffect(() => {
    adminRef.current = admin
  }, [admin])

  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.hidden && adminRef.current) {
        logout()
      }
    }
    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange)
  }, [logout])

  return { admin, error, login, logout }
}

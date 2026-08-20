import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import './MainPage.css'
import googleLoginImg from './assets/Google_login.png'
import kakaoLoginImg from './assets/kakao_login_large_narrow.png'
import naverLoginImg from './assets/NAVER_login_H48.png'

const API_BASE = 'http://localhost:8080'
const TOKEN_KEY = 'accessToken'
const SOCIAL_PROVIDERS = [
  { id: 'google', label: '구글로 시작하기', icon: googleLoginImg },
  { id: 'kakao', label: '카카오로 시작하기', icon: kakaoLoginImg },
  { id: 'naver', label: '네이버로 시작하기', icon: naverLoginImg },
]

const NAV_ITEMS = [
  { label: '마이페이지', path: '/mypage' },
  { label: '자세 측정' },
  { label: '운동 추천' },
]

function LoginModal({ onClose }) {
  useEffect(() => {
    const onKeyDown = (e) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose} aria-label="닫기">×</button>
        <div className="modal-title">WELLMADE 로그인</div>
        <div className="modal-sub">소셜 계정으로 간편하게 시작하세요</div>
        <div className="social-buttons">
          {SOCIAL_PROVIDERS.map((p) => (
            <a key={p.id} className="social-btn" href={`${API_BASE}/oauth2/authorization/${p.id}`}>
              <img src={p.icon} alt={p.label} />
            </a>
          ))}
        </div>
      </div>
    </div>
  )
}

export function useAuth() {
  const [user, setUser] = useState(null)
  const [profile, setProfile] = useState(null)
  const codeExchanged = useRef(false)
  const navigate = useNavigate()

  useEffect(() => {
    const fetchMe = (token) => {
      const authHeader = { Authorization: `Bearer ${token}` }
      fetch(`${API_BASE}/api/users/me`, { headers: authHeader })
        .then((res) => {
          if (!res.ok) throw new Error('unauthorized')
          return res.json()
        })
        .then(setUser)
        .catch(() => {
          localStorage.removeItem(TOKEN_KEY)
          setUser(null)
        })

      fetch(`${API_BASE}/api/users/me/profile`, { headers: authHeader })
        .then((res) => (res.ok ? res.json() : null))
        .then(setProfile)
    }

    const code = new URLSearchParams(window.location.search).get('code')
    if (window.location.pathname === '/oauth/redirect' && code) {
      if (codeExchanged.current) return
      codeExchanged.current = true

      fetch(`${API_BASE}/api/auth/token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code }),
      })
        .then((res) => (res.ok ? res.json() : null))
        .then((data) => {
          if (!data) return
          localStorage.setItem(TOKEN_KEY, data.accessToken)
          navigate('/', { replace: true })
          fetchMe(data.accessToken)
        })
      return
    }

    const token = localStorage.getItem(TOKEN_KEY)
    if (token) fetchMe(token)
  }, [])

  const handleLogout = () => {
    localStorage.removeItem(TOKEN_KEY)
    setUser(null)
    setProfile(null)
  }

  return { user, profile, handleLogout }
}

function Sidebar() {
  const [loginOpen, setLoginOpen] = useState(false)
  const { user, profile, handleLogout } = useAuth()
  const location = useLocation()

  return (
    <>
      <div className="sidebar-hotzone"></div>
      <div className="sidebar-indicator"></div>
      <aside className="sidebar">
        <Link to="/" className="logo">
          <div className="logo-mark"></div>
          <div className="logo-text">WELLMADE</div>
        </Link>
        {user ? (
          <button className="login-btn" onClick={handleLogout}>로그아웃</button>
        ) : (
          <button className="login-btn" onClick={() => setLoginOpen(true)}>로그인</button>
        )}
        <nav className="nav">
          {NAV_ITEMS.map((item) =>
            item.path ? (
              <Link
                key={item.label}
                to={item.path}
                className={`nav-item${location.pathname === item.path ? ' active' : ''}`}
              >
                <span className="dot"></span>
                {item.label}
              </Link>
            ) : (
              <a key={item.label} className="nav-item" href="#">
                <span className="dot"></span>
                {item.label}
              </a>
            )
          )}
        </nav>
        <div className="profile">
          <div className="avatar"></div>
          <div>
            <div className="profile-name">{user ? profile?.name ?? user.email : '게스트'}</div>
            <div className="profile-sub">{user ? '이번주 3회 완료' : '로그인이 필요합니다'}</div>
          </div>
        </div>
      </aside>

      {loginOpen && <LoginModal onClose={() => setLoginOpen(false)} />}
    </>
  )
}

export default Sidebar

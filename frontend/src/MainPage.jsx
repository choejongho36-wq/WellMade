import { useEffect, useState } from 'react'
import './MainPage.css'
import heroBg from './assets/hero-bg.png'
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
  { label: '대시보드', active: true },
  { label: '상세 측정' },
  { label: '인사이트 비교' },
  { label: '운동 추천' },
  { label: '실시간 코칭' },
  { label: '설정' },
]

const PROGRAMS = [
  {
    level: '입문',
    levelClass: 'level',
    weeks: '4주',
    title: '자세 교정 베이직',
    desc: '어깨·골반 불균형을 잡는 기초 루틴과 실시간 피드백으로 시작하는 4주 프로그램.',
  },
  {
    level: '중급',
    levelClass: 'level mid',
    weeks: '6주',
    title: '코어 & 밸런스',
    desc: '체형 데이터 기반 맞춤 루틴으로 코어 안정성과 균형 감각을 함께 끌어올립니다.',
  },
  {
    level: '고급',
    levelClass: 'level high',
    weeks: '8주',
    title: '퍼포먼스 부스트',
    desc: '실시간 스켈레톤 비교 코칭으로 완성된 동작을 훈련하는 심화 프로그램.',
  },
]

function ThumbIcon() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <circle cx="9" cy="9" r="2" />
      <path d="M21 15l-5-5L5 21" />
    </svg>
  )
}

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

function MainPage() {
  const [loginOpen, setLoginOpen] = useState(false)

  const [revealed, setRevealed] = useState(false)
  const [user, setUser] = useState(null)
  const [profile, setProfile] = useState(null)

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
      fetch(`${API_BASE}/api/auth/token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code }),
      })
        .then((res) => res.json())
        .then((data) => {
          localStorage.setItem(TOKEN_KEY, data.accessToken)
          window.history.replaceState({}, '', '/')
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

  return (
    <div className={`app${revealed ? ' revealed' : ''}`}>
      <div className="sidebar-hotzone"></div>
      <div className="sidebar-indicator"></div>
      <aside className="sidebar">
        <div className="logo">
          <div className="logo-mark"></div>
          <div className="logo-text">WELLMADE</div>
        </div>
        {user ? (
          <button className="login-btn" onClick={handleLogout}>로그아웃</button>
        ) : (
          <button className="login-btn" onClick={() => setLoginOpen(true)}>로그인</button>
        )}
        <nav className="nav">
          {NAV_ITEMS.map((item) => (
            <a key={item.label} className={`nav-item${item.active ? ' active' : ''}`} href="#">
              <span className="dot"></span>
              {item.label}
            </a>
          ))}
        </nav>
        <div className="profile">
          <div className="avatar"></div>
          <div>
            <div className="profile-name">{user ? profile?.name ?? user.email : '게스트'}</div>
            <div className="profile-sub">{user ? '이번주 3회 완료' : '로그인이 필요합니다'}</div>
          </div>
        </div>
      </aside>

      <main className="main">
        <section className={`hero${revealed ? ' revealed' : ''}`} style={{ '--hero-bg': `url(${heroBg})` }}>
          <div className="hero-content">
            <h1 className="hero-title">
              WELLMADE<br />YOURSELF
            </h1>
            <button className="hero-reveal-btn" onClick={() => setRevealed(true)} aria-label="더 보기">
              <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                <path d="M6 9l6 6 6-6" />
              </svg>
            </button>
          </div>

          <div className="hero-info">
            <div className="hero-info-eyebrow">AI 운동 코칭 · WELLMADE</div>
            <p className="hero-info-desc">
              상세 측정부터 인사이트 비교, 맞춤 운동 추천, 실시간 코칭까지 — 당신의 몸을 데이터로 읽고
              다음 단계를 제시합니다.
            </p>
            <a className="hero-info-cta" href="#">코칭 프로그램 둘러보기 →</a>
          </div>
        </section>

       
      </main>

      {loginOpen && <LoginModal onClose={() => setLoginOpen(false)} />}
    </div>
  )
}

export default MainPage

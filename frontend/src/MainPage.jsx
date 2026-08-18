import { useEffect, useState } from 'react'
import './MainPage.css'
import heroBg from './assets/hero-bg.png'
import googleLoginImg from './assets/Google_login.png'
import kakaoLoginImg from './assets/kakao_login_large_narrow.png'
import naverLoginImg from './assets/NAVER_login_H48.png'

const API_BASE = 'http://localhost:8080'
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

  return (
    <div className="app">
      <div className="sidebar-hotzone"></div>
      <div className="sidebar-indicator"></div>
      <aside className="sidebar">
        <div className="logo">
          <div className="logo-mark"></div>
          <div className="logo-text">WELLMADE</div>
        </div>
        <button className="login-btn" onClick={() => setLoginOpen(true)}>로그인</button>
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
            <div className="profile-name">회원</div>
            <div className="profile-sub">이번주 3회 완료</div>
          </div>
        </div>
      </aside>

      <main className="main">
        <section className="hero" style={{ '--hero-bg': `url(${heroBg})` }}>
          <h1 className="hero-title">
            WELLMADE<br />YOURSELF
          </h1>
        </section>

        <section className="content">
          <div className="section-head">
            <div>
              <div className="section-eyebrow">PROGRAMS</div>
              <div className="section-title">코칭 프로그램 소개</div>
            </div>
            <a className="section-link" href="#">전체 보기 →</a>
          </div>

          <div className="programs">
            {PROGRAMS.map((p) => (
              <div className="pcard" key={p.title}>
                <div className="pcard-thumb">
                  <ThumbIcon />
                </div>
                <div className="pcard-body">
                  <div className="tag-row">
                    <span className={`tag ${p.levelClass}`}>{p.level}</span>
                    <span className="tag">{p.weeks}</span>
                  </div>
                  <div className="pcard-title">{p.title}</div>
                  <div className="pcard-desc">{p.desc}</div>
                  <a className="pcard-link" href="#">자세히 보기 →</a>
                </div>
              </div>
            ))}
          </div>
        </section>
      </main>

      {loginOpen && <LoginModal onClose={() => setLoginOpen(false)} />}
    </div>
  )
}

export default MainPage

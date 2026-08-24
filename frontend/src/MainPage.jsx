import { useState } from 'react'
import { Link } from 'react-router-dom'
import './MainPage.css'
import heroPhoto from './assets/pngwing.com.png'
import heroBg from './assets/hero-bg.png'
import { NAV_ITEMS, useAuth, LoginModal } from './Sidebar.jsx'
import ChatDrawer from './ChatDrawer.jsx'

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

function MainPage() {
  const [revealed, setRevealed] = useState(false)
  const [loginOpen, setLoginOpen] = useState(false)
  const [chatOpen, setChatOpen] = useState(false)
  const { user, handleLogout, sendChat } = useAuth()

  return (
    <div className={`app${revealed ? ' revealed' : ''}`}>
      <main className="main">
        <section
          className={`hero${revealed ? ' revealed' : ''}`}
          onClick={() => setRevealed(true)}
        >
          <div className="hero-content">
            <h1
              className="hero-title"
              style={{ '--panorama-1': `url(${heroBg})` }}
            >
              WELLMADE<br />YOURSELF
            </h1>
            <p className="hero-reveal-hint">아무 곳이나 클릭하세요</p>
          </div>

          <div className="hero-panel">
            <div className="hero-nav">
              <div className="hero-nav-logo">WELL<span>MADE</span></div>
              <nav className="hero-nav-menu">
                {NAV_ITEMS.map((item) =>
                  item.action === 'chat' ? (
                    <a
                      key={item.label}
                      className="hero-nav-btn"
                      href="#"
                      onClick={(e) => {
                        e.preventDefault()
                        setChatOpen(true)
                      }}
                    >
                      {item.label}
                    </a>
                  ) : item.path ? (
                    <Link key={item.label} to={item.path} className="hero-nav-btn">
                      {item.label}
                    </Link>
                  ) : (
                    <span key={item.label} className="hero-nav-btn disabled">
                      {item.label}
                    </span>
                  )
                )}
              </nav>
              {user ? (
                <button className="hero-nav-login" onClick={handleLogout}>로그아웃</button>
              ) : (
                <button className="hero-nav-login" onClick={() => setLoginOpen(true)}>로그인</button>
              )}
            </div>

            <div className="hero-visual">
              <div className="hero-red-band"></div>
              <div className="hero-photo-wrap">
                <img src={heroPhoto} alt="" className="hero-photo-tint" />
                <img src={heroPhoto} alt="" className="hero-photo-base" />
              </div>
              <span className="hero-photo-index">01</span>
            </div>
          </div>
        </section>
      </main>

      {loginOpen && <LoginModal onClose={() => setLoginOpen(false)} />}
      <ChatDrawer open={chatOpen} onClose={() => setChatOpen(false)} sendChat={sendChat} />
    </div>
  )
}

export default MainPage

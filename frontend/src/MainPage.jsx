import { useState } from 'react'
import './MainPage.css'
import heroBg from './assets/hero-bg.png'
import Sidebar, { TOKEN_KEY } from './Sidebar.jsx'

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
  const [revealed, setRevealed] = useState(() => !!localStorage.getItem(TOKEN_KEY))

  return (
    <div className={`app${revealed ? ' revealed' : ''}`}>
      <Sidebar />

      <main className="main">
        <section
          className={`hero${revealed ? ' revealed' : ''}`}
          style={{ '--hero-bg': `url(${heroBg})` }}
          onClick={() => setRevealed(true)}
        >
          <div className="hero-content">
            <h1 className="hero-title">
              WELLMADE<br />YOURSELF
            </h1>
            <p className="hero-reveal-hint">아무 곳이나 클릭하세요</p>
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
    </div>
  )
}

export default MainPage

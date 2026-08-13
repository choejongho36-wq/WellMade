import './App.css'
import heroBg from './assets/hero-bg.png'

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

function App() {
  return (
    <div className="app">
      <aside className="sidebar">
        <div className="logo">
          <div className="logo-mark"></div>
          <div className="logo-text">WELLMADE</div>
        </div>
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
        <section className="hero" style={{ backgroundImage: `url(${heroBg})` }}>
          <div className="hero-top">
            <div className="badge-live">
              <span className="pulse"></span>AI 자세 분석 연동
            </div>
          </div>
          <div className="eyebrow">AI 운동 코칭 · WELLMADE</div>
          <h1>
            한계를<br />넘어서다
          </h1>
          <p>
            상세 측정부터 인사이트 비교, 맞춤 운동 추천, 실시간 코칭까지 — 당신의 몸을 데이터로 읽고
            다음 단계를 제시합니다.
          </p>
          <div className="hero-cta">
            <a className="btn btn-primary" href="#">코칭 프로그램 둘러보기</a>
            <a className="btn btn-outline" href="#">상세 측정 시작</a>
          </div>
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
    </div>
  )
}

export default App

import { useState } from 'react'
import './MainPage.css'
import heroPhoto from '../assets/pngwing.com.png'
import heroBg from '../assets/hero-bg.png'
import { useAuth } from '../lib/auth.js'
import SiteNav from '../components/SiteNav.jsx'

const HERO_REVEAL_KEY = 'heroRevealedAt'
const HERO_REVEAL_TTL_MS = 30 * 60 * 1000

function wasRecentlyRevealed() {
  const lastRevealedAt = Number(localStorage.getItem(HERO_REVEAL_KEY))
  return Boolean(lastRevealedAt) && Date.now() - lastRevealedAt < HERO_REVEAL_TTL_MS
}

function MainPage() {
  const [revealed, setRevealed] = useState(wasRecentlyRevealed)
  const { user, handleLogout } = useAuth()

  const handleReveal = () => {
    setRevealed(true)
    localStorage.setItem(HERO_REVEAL_KEY, String(Date.now()))
  }

  return (
    <div className={`app${revealed ? ' revealed' : ''}`}>
      <main className="main">
        <section
          className={`hero${revealed ? ' revealed' : ''}`}
          onClick={handleReveal}
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
              <SiteNav user={user} onLogout={handleLogout} />
            </div>

            <div className="hero-visual">
              <div className="hero-red-band"></div>
              <p className="hero-tagline-lines">
                <span className="hero-tagline-small">For a</span>Better
              </p>
              <p className="hero-tagline-big">Tomorrow</p>
              <div className="hero-photo-wrap">
                <img src={heroPhoto} alt="" className="hero-photo-tint" />
                <img src={heroPhoto} alt="" className="hero-photo-base" />
              </div>
              <span className="hero-photo-index">01</span>
            </div>
          </div>
        </section>
      </main>
    </div>
  )
}

export default MainPage

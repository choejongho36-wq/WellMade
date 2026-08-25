import { Link } from 'react-router-dom'
import './SiteNav.css'
import { NAV_ITEMS, SOCIAL_PROVIDERS, API_BASE } from '../lib/auth.js'

function SiteNav({ user, onLogout, onChatClick }) {
  return (
    <>
      <Link to="/" className="hero-nav-logo">WELL<span>MADE</span></Link>
      {user ? (
        <>
          <nav className="hero-nav-menu">
            {NAV_ITEMS.map((item) =>
              item.action === 'chat' ? (
                <a
                  key={item.label}
                  className="hero-nav-btn"
                  href="#"
                  onClick={(e) => {
                    e.preventDefault()
                    onChatClick()
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
          <button className="hero-nav-login" onClick={onLogout}>로그아웃</button>
        </>
      ) : (
        <div className="hero-social-login">
          {SOCIAL_PROVIDERS.map((p) => (
            <a
              key={p.id}
              className="social-btn"
              style={{ background: p.bg, color: p.color }}
              href={`${API_BASE}/oauth2/authorization/${p.id}`}
            >
              <img src={p.icon} alt="" />
              {p.label}
            </a>
          ))}
        </div>
      )}
    </>
  )
}

export default SiteNav

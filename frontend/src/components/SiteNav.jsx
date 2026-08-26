import { Link } from 'react-router-dom'
import './SiteNav.css'
import { NAV_ITEMS, SOCIAL_PROVIDERS, API_BASE } from '../lib/auth.js'

function SiteNav({ user, onLogout }) {
  return (
    <>
      <Link to="/" className="nav-logo">WELL<span>MADE</span></Link>
      {user ? (
        <>
          <nav className="nav-menu">
            {NAV_ITEMS.map((item) =>
              item.path ? (
                <Link key={item.label} to={item.path} className="nav-btn">
                  {item.label}
                </Link>
              ) : (
                <span key={item.label} className="nav-btn disabled">
                  {item.label}
                </span>
              )
            )}
          </nav>
          <button className="nav-btn nav-logout" onClick={onLogout}>로그아웃</button>
        </>
      ) : (
        <div className="nav-social">
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

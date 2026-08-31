import './PageShell.css'
import { useAuth } from '../lib/auth.js'
import SiteNav from './SiteNav.jsx'

function PageShell({ children, showNav = true }) {
  const { user, handleLogout } = useAuth()

  return (
    <div className="page-shell">
      {showNav && (
        <div className="page-shell-nav">
          <SiteNav user={user} onLogout={handleLogout} />
        </div>
      )}
      <div className={showNav ? 'page-shell-content' : 'page-shell-content page-shell-content--full'}>
        {children}
      </div>
    </div>
  )
}

export default PageShell

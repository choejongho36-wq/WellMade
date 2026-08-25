import './PageShell.css'
import { useAuth } from '../lib/auth.js'
import SiteNav from './SiteNav.jsx'

function PageShell({ children }) {
  const { user, handleLogout } = useAuth()

  return (
    <div className="page-shell">
      <div className="page-shell-nav">
        <SiteNav user={user} onLogout={handleLogout} />
      </div>
      <div className="page-shell-content">{children}</div>
    </div>
  )
}

export default PageShell

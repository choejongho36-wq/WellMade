import { useState } from 'react'
import './PageShell.css'
import { useAuth } from '../lib/auth.js'
import SiteNav from './SiteNav.jsx'
import ChatDrawer from './ChatDrawer.jsx'

function PageShell({ children }) {
  const [chatOpen, setChatOpen] = useState(false)
  const { user, handleLogout, sendChat } = useAuth()

  return (
    <div className="page-shell">
      <div className="page-shell-nav">
        <SiteNav user={user} onLogout={handleLogout} onChatClick={() => setChatOpen(true)} />
      </div>
      <div className="page-shell-content">{children}</div>

      <ChatDrawer open={chatOpen} onClose={() => setChatOpen(false)} sendChat={sendChat} />
    </div>
  )
}

export default PageShell

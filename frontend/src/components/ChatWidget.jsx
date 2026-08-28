import { useState } from 'react'
import ChatDrawer from './ChatDrawer.jsx'
import RobotIcon from './RobotIcon.jsx'
import './ChatWidget.css'

function ChatWidget({ loggedIn, sendChat, getChatHistory, getNutrientAdvice, userName }) {
  const [open, setOpen] = useState(false)

  return (
    <>
      <button className="chat-fab" onClick={() => setOpen((o) => !o)} aria-label={open ? '챗봇 닫기' : '챗봇 열기'}>
        <RobotIcon size={26} color="#111" />
        <span className="chat-fab-label">CHAT</span>
      </button>
      <ChatDrawer
        open={open}
        loggedIn={loggedIn}
        onClose={() => setOpen(false)}
        sendChat={sendChat}
        getChatHistory={getChatHistory}
        getNutrientAdvice={getNutrientAdvice}
        userName={userName}
      />
    </>
  )
}

export default ChatWidget

import { useState } from 'react'
import ChatDrawer from './ChatDrawer.jsx'
import chatbotIcon from '../assets/Wellmade chatbot.png'
import './ChatWidget.css'

function ChatWidget({ loggedIn, sendChat, getChatHistory, clearChatHistory, getNutrientAdvice, userName }) {
  const [open, setOpen] = useState(false)

  return (
    <>
      <button className="chat-fab" onClick={() => setOpen((o) => !o)} aria-label={open ? '챗봇 닫기' : '챗봇 열기'}>
        <img className="chat-fab-icon" src={chatbotIcon} alt="" />
      </button>
      <ChatDrawer
        open={open}
        loggedIn={loggedIn}
        onClose={() => setOpen(false)}
        sendChat={sendChat}
        getChatHistory={getChatHistory}
        clearChatHistory={clearChatHistory}
        getNutrientAdvice={getNutrientAdvice}
        userName={userName}
      />
    </>
  )
}

export default ChatWidget

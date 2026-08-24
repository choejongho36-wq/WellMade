import { useEffect, useRef, useState } from 'react'
import './MainPage.css'

function ChatDrawer({ open, onClose, sendChat }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const bottomRef = useRef(null)

  useEffect(() => {
    if (open) bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading, open])

  useEffect(() => {
    const onKeyDown = (e) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  const handleSend = () => {
    const text = input.trim()
    if (!text || loading) return

    const nextMessages = [...messages, { role: 'user', content: text }]
    setMessages(nextMessages)
    setInput('')
    setLoading(true)
    setError('')

    sendChat(nextMessages)
      .then((reply) => {
        setMessages((prev) => [...prev, { role: 'assistant', content: reply }])
      })
      .catch(() => setError('답변을 받지 못했어요. 잠시 후 다시 시도해주세요.'))
      .finally(() => setLoading(false))
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className={`chat-drawer-backdrop${open ? ' open' : ''}`} onClick={onClose}>
      <div className="chat-drawer" onClick={(e) => e.stopPropagation()}>
        <div className="chat-drawer-header">
          <div className="chat-drawer-title">WELL<span>MADE</span> 챗봇</div>
          <button className="chat-drawer-close" onClick={onClose} aria-label="닫기">×</button>
        </div>

        <div className="chat-drawer-messages">
          {messages.length === 0 && (
            <p className="chat-drawer-hint">목표와 인바디 기록을 바탕으로 조언해드려요. 편하게 물어보세요.</p>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`chat-bubble-row ${m.role}`}>
              <div className="chat-bubble">{m.content}</div>
            </div>
          ))}
          {loading && (
            <div className="chat-bubble-row assistant">
              <div className="chat-bubble chat-bubble-loading">생각하는 중...</div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {error && <p className="chat-drawer-error">{error}</p>}

        <div className="chat-input-row">
          <textarea
            className="chat-input"
            rows={1}
            placeholder="메시지를 입력하세요"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={loading}
          />
          <button className="chat-send-btn" onClick={handleSend} disabled={loading || !input.trim()}>
            전송
          </button>
        </div>
      </div>
    </div>
  )
}

export default ChatDrawer

import { useEffect, useRef, useState } from 'react'
import './ChatDrawer.css'

const CHAT_STARTERS = [
  {
    id: 'diet',
    label: '식단에 대해 조언을 받고싶어',
    followUp: '어떤 메뉴를 드실 예정이신가요?',
  },
  {
    id: 'workout',
    label: '오늘 할 운동을 추천받고싶어',
  },
  {
    id: 'goal-check',
    label: '지금 페이스가 목표에 맞는지 궁금해',
  },
]

function ChatDrawer({ open, onClose, sendChat }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [pendingFollowUp, setPendingFollowUp] = useState(null)
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

  const sendMessage = (content, display) => {
    if (loading) return

    const nextMessages = [...messages, { role: 'user', content, display }]
    setMessages(nextMessages)
    setInput('')
    setPendingFollowUp(null)
    setLoading(true)
    setError('')

    sendChat(nextMessages.map(({ role, content }) => ({ role, content })))
      .then((reply) => {
        setMessages((prev) => [...prev, { role: 'assistant', content: reply }])
      })
      .catch(() => setError('답변을 받지 못했어요. 잠시 후 다시 시도해주세요.'))
      .finally(() => setLoading(false))
  }

  const handleStarterClick = (starter) => {
    if (loading) return

    if (starter.followUp) {
      setMessages((prev) => [
        ...prev,
        { role: 'user', content: starter.label },
        { role: 'assistant', content: starter.followUp },
      ])
      setPendingFollowUp(starter)
      return
    }

    sendMessage(starter.label)
  }

  const handleSend = () => {
    const text = input.trim()
    if (!text || loading) return

    if (pendingFollowUp) {
      sendMessage(
        `오늘 ${text}을(를) 먹으려고 하는데, 제 목표와 최근 인바디 수치에 맞춰서 괜찮은지, 어떻게 곁들이면 좋을지 조언해줘.`,
        text
      )
      return
    }

    sendMessage(text)
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
          <div className="chat-drawer-title">WELL<span>MADE</span></div>
          <button className="chat-drawer-close" onClick={onClose} aria-label="닫기">×</button>
        </div>

        <div className="chat-drawer-messages">
          {messages.length === 0 && (
            <>
              <p className="chat-drawer-hint">인바디 기록을 바탕으로 조언해드려요. 아래에서 골라보거나 편하게 물어보세요.</p>
              <div className="chat-starter-list">
                {CHAT_STARTERS.map((s) => (
                  <button key={s.id} className="chat-starter-btn" onClick={() => handleStarterClick(s)}>
                    {s.label}
                  </button>
                ))}
              </div>
            </>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`chat-bubble-row ${m.role}`}>
              <div className="chat-bubble">{m.display ?? m.content}</div>
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
            placeholder={pendingFollowUp ? '예: 김치찌개' : '메시지를 입력하세요'}
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

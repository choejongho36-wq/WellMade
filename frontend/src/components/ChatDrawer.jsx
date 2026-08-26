import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import RobotIcon from './RobotIcon.jsx'
import './ChatDrawer.css'

// 나머지 메뉴는 관련 기능이 추가되는 대로 여기에 이어서 추가
const CHAT_MENU_ITEMS = [
  { id: 'diet-manage', label: '나의 식단 관리', path: '/mealplan' },
  { id: 'nutrient-advice', label: '오늘 영양소 분석', action: 'nutrient-advice' },
]

function ChatDrawer({ open, onClose, sendChat, getChatHistory, getNutrientAdvice, userName }) {
  const greeting = `안녕하세요, ${userName ?? '회원'}님 반갑습니다.\n궁금하신 내용을 선택해주세요.`
  const navigate = useNavigate()
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [pendingFollowUp, setPendingFollowUp] = useState(null)
  const [historyLoaded, setHistoryLoaded] = useState(false)
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

  // 드로어를 처음 열 때 서버에 저장된 이전 대화를 한 번 불러옴 - 새로고침/재접속해도 이어서 보임
  useEffect(() => {
    if (open && !historyLoaded) {
      setHistoryLoaded(true)
      getChatHistory()
        .then((history) => {
          if (history.length) {
            setMessages(history.map((h) => ({ role: h.role, content: h.content })))
          }
        })
        .catch(() => {}) // 이력 로드 실패는 조용히 무시 - 새 대화 시작하듯 진행하면 됨
    }
  }, [open, historyLoaded, getChatHistory])

  const sendMessage = (content, display) => {
    if (loading) return

    setMessages((prev) => [...prev, { role: 'user', content, display }])
    setInput('')
    setPendingFollowUp(null)
    setLoading(true)
    setError('')

    // 대화 이력은 서버(DB)가 갖고 있으므로 새 메시지 하나만 보내면 됨
    sendChat(content)
      .then((reply) => {
        setMessages((prev) => [...prev, { role: 'assistant', content: reply }])
      })
      .catch(() => setError('답변을 받지 못했어요. 잠시 후 다시 시도해주세요.'))
      .finally(() => setLoading(false))
  }

  const handleMenuClick = (item) => {
    if (loading) return

    if (item.path) {
      onClose()
      navigate(item.path)
      return
    }

    if (item.action === 'nutrient-advice') {
      setMessages((prev) => [...prev, { role: 'user', content: item.label }])
      setLoading(true)
      setError('')
      getNutrientAdvice()
        .then((reply) => {
          setMessages((prev) => [...prev, { role: 'assistant', content: reply }])
        })
        .catch((e) => setError(e.message || '분석을 받지 못했어요. 잠시 후 다시 시도해주세요.'))
        .finally(() => setLoading(false))
      return
    }

    if (item.followUp) {
      setMessages((prev) => [
        ...prev,
        { role: 'user', content: item.label },
        { role: 'assistant', content: item.followUp },
      ])
      setPendingFollowUp(item)
      return
    }

    sendMessage(item.label)
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
              <div className="chat-greeting-row">
                <div className="chat-greeting-avatar">
                  <RobotIcon size={36} />
                </div>
                <p className="chat-drawer-hint">{greeting}</p>
              </div>
              <div className="chat-starter-list">
                {CHAT_MENU_ITEMS.map((item) => (
                  <button key={item.id} className="chat-starter-btn" onClick={() => handleMenuClick(item)}>
                    {item.label}
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

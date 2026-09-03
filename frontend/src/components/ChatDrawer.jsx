import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import chatbotIcon from '../assets/Wellmade chatbot.png'
import './ChatDrawer.css'

// 예전에는 send 문장을 그대로 모델에게 보내고 모델이 알아서 도구를 고르길 기대했는데, 그 "고르기"가
// 확률적으로 실패했다(툴콜을 텍스트로 흘리거나 아예 안 부르고 지어냄). 버튼을 누른 시점에 이미 어떤
// 데이터를 볼지는 정해져 있으므로, 이제 menu:true 항목은 id를 서버로 보내고 서버가 도구를 직접 실행한다
// (ChatService.menuReply). 모델은 결과를 문장으로 옮기는 일만 하고, 기록이 없으면 아예 호출되지 않는다.
//
// label은 버튼에 보이는 짧은 이름, send는 화면에 먼저 그릴 사용자 말풍선 문구다.
// send는 서버가 이력에 저장하는 문구(ChatService.menuTool의 userLabel)와 맞춰야 새로고침 후에도 같아 보인다.
const CHAT_MENU_ITEMS = [
  { id: 'meals-today', label: '오늘 식단', send: '오늘 뭐 먹었지?', menu: true },
  { id: 'meals-yesterday', label: '어제 식단', send: '어제 먹은 거 보여줘', menu: true },
  { id: 'total-today', label: '오늘 섭취량', send: '오늘 총 섭취량 알려줘', menu: true },
  { id: 'target', label: '목표 섭취량', send: '내 목표 섭취량 알려줘', menu: true },
  { id: 'inbody-trend', label: '체중 추세', send: '요즘 체중 변화 어때?', menu: true },
  // 전용 API(/nutrient-advice) - 목표 대비 분석을 서버가 계산해서 넘긴다
  { id: 'nutrient-advice', label: '영양소 분석', action: 'nutrient-advice' },
  // 운동 추천: 버튼 -> 봇이 부위/난이도를 되묻고(followUp) -> 사용자 답을 wrap으로 감싸
  // 일반 채팅으로 보냄. 서버가 recommend_exercises 도구를 호출해 후보를 가져오고 모델이 추천문을 만든다.
  {
    id: 'exercise-recommend',
    label: '운동 추천',
    send: '운동 추천받고 싶어요',
    followUp: '어느 부위를 운동하고 싶으세요? 초급/중급 같은 난이도나 사용할 장비(맨몸, 덤벨 등)가 있으면 같이 알려주세요.',
    placeholder: '예: 하체, 중급, 맨몸',
    wrap: (t) => `운동을 추천받고 싶어요. 원하는 조건: ${t}`,
  },
  { id: 'diet-manage', label: '캘린더', path: '/mealplan' },
]

// 로딩 인디케이터: 글자 -> 점 순서로 물결이 흐르도록 한 칸씩 지연을 준다
const THINKING_TEXT = [...'생각하는 중']
const TYPING_STEP_SEC = 0.09

function ChatDrawer({ open, loggedIn, onClose, sendChat, getChatHistory, clearChatHistory, getNutrientAdvice, sendChatMenu, userName }) {
  const navigate = useNavigate()
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [pendingFollowUp, setPendingFollowUp] = useState(null)
  const [historyLoaded, setHistoryLoaded] = useState(false)
  const [clearing, setClearing] = useState(false)
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
    if (open && loggedIn && !historyLoaded) {
      setHistoryLoaded(true)
      getChatHistory()
        .then((history) => {
          if (history.length) {
            setMessages(history.map((h) => ({ role: h.role, content: h.content })))
          }
        })
        // 조용히 넘기면 "대화가 사라진 것"처럼 보인다. 새 대화는 계속 할 수 있으므로
        // 화면을 막지는 않고 안내만 띄운다
        .catch(() => setError('이전 대화를 불러오지 못했어요. 새로 시작할 수는 있어요.'))
    }
  }, [open, loggedIn, historyLoaded, getChatHistory])

  // 로그아웃하면(세션 만료 포함) 남의 대화가 남지 않도록 비우고, 다음 로그인 때 다시 불러오게 함
  useEffect(() => {
    if (!loggedIn) {
      setMessages([])
      setError('')
      setHistoryLoaded(false)
    }
  }, [loggedIn])

  const sendMessage = (content, display) => {
    if (loading) return

    setMessages((prev) => [...prev, { role: 'user', content, display }])
    setInput('')
    setPendingFollowUp(null)
    setLoading(true)
    setError('')

    // 대화 이력은 서버(DB)가 갖고 있으므로 새 메시지 하나만 보내면 됨.
    // 응답은 스트리밍 - 토큰이 올 때마다 마지막 assistant 말풍선을 갱신함
    const applyStream = (partial) => {
      setMessages((prev) => {
        const copy = [...prev]
        const last = copy[copy.length - 1]
        if (last?.role === 'assistant' && last.streaming) {
          copy[copy.length - 1] = { ...last, content: partial }
        } else {
          copy.push({ role: 'assistant', content: partial, streaming: true })
        }
        return copy
      })
    }

    sendChat(content, applyStream)
      .then((reply) => {
        setMessages((prev) => {
          const copy = [...prev]
          const last = copy[copy.length - 1]
          if (last?.role === 'assistant' && last.streaming) {
            copy[copy.length - 1] = { role: 'assistant', content: reply }
          } else {
            copy.push({ role: 'assistant', content: reply })
          }
          return copy
        })
      })
      .catch((e) => setError(e.message || '답변을 받지 못했어요. 잠시 후 다시 시도해주세요.'))
      .finally(() => setLoading(false))
  }

  const handleMenuClick = (item) => {
    if (loading) return

    if (item.path) {
      onClose()
      navigate(item.path)
      return
    }

    if (item.menu) {
      setMessages((prev) => [...prev, { role: 'user', content: item.send ?? item.label }])
      setLoading(true)
      setError('')
      sendChatMenu(item.id)
        .then((reply) => {
          setMessages((prev) => [...prev, { role: 'assistant', content: reply }])
        })
        .catch((e) => setError(e.message || '답변을 받지 못했어요. 잠시 후 다시 시도해주세요.'))
        .finally(() => setLoading(false))
      return
    }

    if (item.action === 'nutrient-advice') {
      setMessages((prev) => [...prev, { role: 'user', content: item.send ?? item.label }])
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
        { role: 'user', content: item.send ?? item.label },
        { role: 'assistant', content: item.followUp },
      ])
      setPendingFollowUp(item)
      return
    }

    sendMessage(item.send ?? item.label)
  }

  const handleSend = () => {
    const text = input.trim()
    if (!text || loading) return

    if (pendingFollowUp) {
      // wrap이 있으면 사용자 답을 문맥 문장으로 감싸 모델에게 보내고(말풍선엔 원문만 표시),
      // 없으면 원문 그대로 보낸다.
      const { wrap } = pendingFollowUp
      sendMessage(wrap ? wrap(text) : text, text)
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

  // 확인 없이 지우면 되돌릴 수 없어서 한 번 물어본다 (서버에서 완전 삭제됨)
  const handleClearHistory = () => {
    if (!window.confirm('대화 기록을 모두 지울까요? 되돌릴 수 없어요.')) return

    setClearing(true)
    setError('')
    clearChatHistory()
      .then(() => {
        setMessages([])
        setPendingFollowUp(null)
      })
      .catch((e) => setError(e.message || '대화 기록을 지우지 못했어요'))
      .finally(() => setClearing(false))
  }

  return (
    <div className={`chat-drawer-backdrop${open ? ' open' : ''}`} onClick={onClose}>
      <div className="chat-drawer" onClick={(e) => e.stopPropagation()}>
        <div className="chat-drawer-header">
          <div className="chat-drawer-title">WELL<span>MADE</span></div>
          {/* 이력은 다음 답변의 맥락으로도 쓰이므로, 지우면 말투까지 새 대화로 초기화된다 */}
          {loggedIn && messages.length > 0 && (
            <button className="chat-drawer-clear" onClick={handleClearHistory} disabled={clearing}>
              {clearing ? '지우는 중...' : '대화 기록 지우기'}
            </button>
          )}
          <button className="chat-drawer-close" onClick={onClose} aria-label="닫기">×</button>
        </div>

        <div className="chat-drawer-body">
          {/* 비로그인 상태에서는 아래 내용을 통째로 덮고, inert로 클릭·탭 이동까지 막는다 */}
          {!loggedIn && (
            <div className="chat-login-overlay">
              <img className="chat-login-overlay-icon" src={chatbotIcon} alt="" />
              <p className="chat-login-overlay-title">로그인이 필요해요</p>
              <p className="chat-login-overlay-sub">
                
              </p>
            </div>
          )}

          <div className="chat-drawer-inner" inert={!loggedIn}>
            <div className="chat-drawer-messages">
              {messages.length === 0 && (
                <>
                  <div className="chat-greeting-row">
                    <div className="chat-greeting-avatar">
                      <img className="chat-bot-img" src={chatbotIcon} alt="" />
                    </div>
                    <p className="chat-drawer-hint">
                      안녕하세요, <span className="chat-greeting-name">{userName ?? '회원'}</span>님 반갑습니다.
                      <br />궁금하신 내용을 선택해주세요.
                    </p>
                  </div>
                </>
              )}
              {messages.map((m, i) => (
                <div key={i} className={`chat-bubble-row ${m.role}`}>
                  {/* 누가 한 말인지 말풍선마다 보이도록 챗봇 답변 옆에 아이콘을 붙인다.
                      같은 화자가 연달아 말하면 첫 줄에만 아이콘을 두고 나머지는 자리만 비운다 */}
                  {m.role === 'assistant' && (
                    <div className="chat-bubble-avatar">
                      {messages[i - 1]?.role !== 'assistant' && <img className="chat-bot-img" src={chatbotIcon} alt="" />}
                    </div>
                  )}
                  <div className="chat-bubble">{m.display ?? m.content}</div>
                </div>
              ))}
              {loading && !messages[messages.length - 1]?.streaming && (
                <div className="chat-bubble-row assistant">
                  <div className="chat-bubble-avatar">
                    {messages[messages.length - 1]?.role !== 'assistant' && <img className="chat-bot-img" src={chatbotIcon} alt="" />}
                  </div>
                  {/* 글자 대신 점 세 개가 차례로 튀는 타이핑 인디케이터.
                      스크린리더는 aria-label로 상태를 읽고, 점 자체는 aria-hidden으로 숨긴다 */}
                  {/* 글자와 점이 하나의 물결로 이어지도록 글자를 한 자씩 쪼개서
                      같은 애니메이션에 순서대로 지연을 준다. 글자를 쪼개면 스크린리더가
                      낱자로 읽으므로 wrapper의 aria-label로 문구 전체를 대신 읽힌다 */}
                  <div className="chat-bubble chat-bubble-loading" role="status">
                    <span className="chat-typing-text" aria-label="생각하는 중">
                      {THINKING_TEXT.map((ch, i) => (
                        <span
                          key={i}
                          className="chat-typing-char"
                          style={{ animationDelay: `${i * TYPING_STEP_SEC}s` }}
                        >
                          {ch === ' ' ? ' ' : ch}
                        </span>
                      ))}
                    </span>
                    <span className="chat-typing" aria-hidden="true">
                      {[0, 1, 2].map((i) => (
                        <span
                          key={i}
                          style={{ animationDelay: `${(THINKING_TEXT.length + i) * TYPING_STEP_SEC}s` }}
                        />
                      ))}
                    </span>
                  </div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>

            {error && <p className="chat-drawer-error">{error}</p>}

            <div className="chat-input-row">
              <textarea
                className="chat-input"
                rows={1}
                placeholder={pendingFollowUp ? (pendingFollowUp.placeholder ?? '예: 김치찌개') : '메시지를 입력하세요'}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={loading}
              />
              <button className="chat-send-btn" onClick={handleSend} disabled={loading || !input.trim()}>
                전송
              </button>
            </div>
            {/* 대화 중에도 계속 보이는 바로가기. 누르면 그대로 내 메시지가 되므로
                사용자 말풍선과 같은 모양(레드·우하단 각)으로 두고 입력창 아래에 붙인다 */}
            <div className="chat-quick-menu">
              {CHAT_MENU_ITEMS.map((item) => (
                <button
                  key={item.id}
                  className="chat-quick-btn"
                  onClick={() => handleMenuClick(item)}
                  disabled={loading}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default ChatDrawer

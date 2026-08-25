import { useEffect, useState } from 'react'
import './DietPage.css'
import '../components/ChatDrawer.css'
import { useAuth } from '../lib/auth.js'
import PageShell from '../components/PageShell.jsx'

const MEAL_TYPE_LABEL = {
  BREAKFAST: '아침',
  LUNCH: '점심',
  DINNER: '저녁',
  SNACK: '간식',
}

function DietPage() {
  const { user, logMeal, getTodayMeals, getTodayTotal } = useAuth()
  const [meals, setMeals] = useState([])
  const [total, setTotal] = useState(null)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [notice, setNotice] = useState('')

  const refresh = () => {
    getTodayMeals().then(setMeals).catch(() => {})
    getTodayTotal().then(setTotal).catch(() => {})
  }

  useEffect(() => {
    if (user) refresh()
  }, [user])

  const handleLog = () => {
    const text = input.trim()
    if (!text || loading) return

    setLoading(true)
    setNotice('')
    logMeal(text)
      .then((result) => {
        setInput('')
        refresh()
        if (result.notFoundFoods?.length) {
          setNotice(`DB에서 찾지 못한 음식: ${result.notFoundFoods.join(', ')}`)
        }
      })
      .catch((e) => setNotice(e.message || '식단 기록에 실패했어요'))
      .finally(() => setLoading(false))
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleLog()
    }
  }

  return (
    <PageShell>
      <div className="mp-eyebrow-row">
        <div className="mp-index-tag">식단 관리</div>
      </div>

      {user ? (
        <>
          {total && (
            <p className="pcard-desc" style={{ marginTop: 20 }}>
              오늘 총 {Math.round(total.totalCalories)}kcal · 단백질 {total.totalProteinG.toFixed(1)}g
              {' '}· 탄수화물 {total.totalCarbsG.toFixed(1)}g · 지방 {total.totalFatG.toFixed(1)}g
            </p>
          )}

          <div className="chat-input-row">
            <textarea
              className="chat-input"
              rows={1}
              placeholder="오늘 뭐 드셨나요? (예: 점심에 김치찌개랑 밥 한공기 먹었어요)"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={loading}
            />
            <button className="chat-send-btn" onClick={handleLog} disabled={loading || !input.trim()}>
              {loading ? '기록 중...' : '기록하기'}
            </button>
          </div>
          {notice && <p className="chat-drawer-error">{notice}</p>}

          <div className="diet-timeline" style={{ marginTop: 20 }}>
            {meals.length === 0 && <p className="pcard-desc">오늘 기록된 식사가 없어요.</p>}
            {meals.map((meal) => (
              <div className="diet-row" key={meal.id}>
                <div className="diet-time">
                  {new Date(meal.created_at).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })}
                </div>
                <div className="diet-line">
                  <div className="diet-dot"></div>
                </div>
                <div className="diet-body">
                  <div className="diet-meal">
                    <div className="diet-meal-inner">
                      <div className="diet-meal-thumb"></div>
                      <div style={{ flex: 1 }}>
                        <div className="diet-meal-title">
                          {MEAL_TYPE_LABEL[meal.meal_type] ?? meal.meal_type} · {meal.menu_name}
                        </div>
                        <div className="diet-meal-sub">{meal.kcal}kcal</div>
                      </div>
                      <div className="diet-meal-status">기록됨</div>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </>
      ) : (
        <p className="pcard-desc" style={{ marginTop: 20 }}>로그인 후 식단을 기록할 수 있습니다.</p>
      )}
    </PageShell>
  )
}

export default DietPage

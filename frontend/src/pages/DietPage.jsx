import { useEffect, useState } from 'react'
import './DietPage.css'
import '../components/ChatDrawer.css'
import { useAuth } from '../lib/auth.js'
import PageShell from '../components/PageShell.jsx'
import Calendar from '../components/Calendar.jsx'
import NutrientDetailModal from '../components/NutrientDetailModal.jsx'

const MEAL_TYPE_LABEL = {
  BREAKFAST: '아침',
  LUNCH: '점심',
  DINNER: '저녁',
  SNACK: '간식',
}

function todayStr() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

const SUMMARY_HEADLINE_FIELD = { key: 'totalCalories', label: '칼로리', unit: 'kcal' }

function DietPage() {
  const { user, logMeal, getTodayMeals, getTodayTotal, updateMeal, deleteMeal } = useAuth()
  const [selectedDate, setSelectedDate] = useState(todayStr)
  const [mealType, setMealType] = useState('')
  const [meals, setMeals] = useState([])
  const [total, setTotal] = useState(null)
  const [todaySummary, setTodaySummary] = useState(null)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [notice, setNotice] = useState('')
  const [notFoundFoods, setNotFoundFoods] = useState(null)
  const [editingId, setEditingId] = useState(null)
  const [editDraft, setEditDraft] = useState({ mealType: '', menuName: '', kcal: '' })
  const [savingEdit, setSavingEdit] = useState(false)
  const [deletingId, setDeletingId] = useState(null)
  const [nutrientModalOpen, setNutrientModalOpen] = useState(false)

  const isToday = selectedDate === todayStr()

  const refresh = (date) => {
    getTodayMeals(date).then(setMeals).catch(() => {})
    getTodayTotal(date).then(setTotal).catch(() => {})
  }

  const refreshTodaySummary = () => {
    getTodayTotal(todayStr()).then(setTodaySummary).catch(() => {})
  }

  useEffect(() => {
    if (user) refresh(selectedDate)
  }, [user, selectedDate])

  useEffect(() => {
    if (user) refreshTodaySummary()
  }, [user])

  const handleLog = () => {
    const text = input.trim()
    if (!text || loading) return

    setLoading(true)
    setNotice('')
    logMeal(text, mealType)
      .then((result) => {
        refresh(selectedDate)
        refreshTodaySummary()
        if (result.notFoundFoods?.length) {
          setNotFoundFoods(result.notFoundFoods)
        } else {
          setInput('')
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

  const startEdit = (meal) => {
    setEditingId(meal.id)
    setEditDraft({ mealType: meal.meal_type, menuName: meal.menu_name, kcal: meal.kcal })
  }

  const cancelEdit = () => setEditingId(null)

  const saveEdit = (id) => {
    setSavingEdit(true)
    updateMeal(id, { ...editDraft, kcal: Number(editDraft.kcal) || 0 })
      .then(() => {
        setEditingId(null)
        refresh(selectedDate)
        refreshTodaySummary()
      })
      .catch((e) => setNotice(e.message || '수정에 실패했어요'))
      .finally(() => setSavingEdit(false))
  }

  const handleDelete = (id) => {
    if (!window.confirm('이 기록을 삭제할까요?')) return

    setDeletingId(id)
    deleteMeal(id)
      .then(() => {
        refresh(selectedDate)
        refreshTodaySummary()
      })
      .catch((e) => setNotice(e.message || '삭제에 실패했어요'))
      .finally(() => setDeletingId(null))
  }

  return (
    <PageShell>
      <div className="mp-eyebrow-row">
        <div className="mp-index-tag">Meal plan</div>
      </div>

      {user ? (
        <>
          <div className="diet-split">
            <div className="diet-col-left">
              <Calendar selected={selectedDate} onSelect={setSelectedDate} maxDateStr={todayStr()} />

              {isToday ? (
                <div className="diet-log-form">
                  <select
                    className="diet-mealtype-select"
                    value={mealType}
                    onChange={(e) => setMealType(e.target.value)}
                    disabled={loading}
                  >
                    <option value="">자동 (시간대로 추정)</option>
                    {Object.entries(MEAL_TYPE_LABEL).map(([value, label]) => (
                      <option key={value} value={value}>{label}</option>
                    ))}
                  </select>
                  <textarea
                    className="chat-input"
                    rows={3}
                    placeholder="언제 뭘 드셨나요? (예: 점심에 김치찌개랑 밥 한공기 먹었어요)"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    disabled={loading}
                  />
                  <button className="chat-send-btn" onClick={handleLog} disabled={loading || !input.trim()}>
                    {loading ? '기록 중...' : '기록하기'}
                  </button>
                </div>
              ) : (
                <p className="pcard-desc" style={{ marginTop: 16 }}>
                  지난 기록을 보고 있어요. 새로 기록하려면 오늘 날짜를 선택하세요.
                </p>
              )}
              {notice && <p className="chat-drawer-error">{notice}</p>}
            </div>

            <div className="diet-col-right">
              <div className="mp-section-head">
                <div className="mp-section-title">기록한 메뉴</div>
              </div>
              

              <div className="diet-timeline" style={{ marginTop: 14 }}>
                {meals.length === 0 && (
                  <p className="pcard-desc">{isToday ? '오늘' : '이 날'} 기록된 식사가 없어요.</p>
                )}
                {meals.map((meal) => (
                  <div className="diet-row" key={meal.id}>
                    <div className="diet-time">
                      {MEAL_TYPE_LABEL[meal.meal_type] ?? meal.meal_type}
                    </div>
                    <div className="diet-line">
                      <div className="diet-dot"></div>
                    </div>
                    <div className="diet-body">
                      <div className="diet-meal">
                        {editingId === meal.id ? (
                          <div className="diet-meal-edit">
                            <select
                              className="diet-mealtype-select"
                              value={editDraft.mealType}
                              onChange={(e) => setEditDraft((d) => ({ ...d, mealType: e.target.value }))}
                              disabled={savingEdit}
                            >
                              {Object.entries(MEAL_TYPE_LABEL).map(([value, label]) => (
                                <option key={value} value={value}>{label}</option>
                              ))}
                            </select>
                            <input
                              className="diet-meal-edit-input"
                              type="text"
                              value={editDraft.menuName}
                              onChange={(e) => setEditDraft((d) => ({ ...d, menuName: e.target.value }))}
                              disabled={savingEdit}
                            />
                            <input
                              className="diet-meal-edit-input diet-meal-edit-kcal"
                              type="number"
                              value={editDraft.kcal}
                              onChange={(e) => setEditDraft((d) => ({ ...d, kcal: e.target.value }))}
                              disabled={savingEdit}
                            />
                            <div className="diet-meal-edit-actions">
                              <button className="mp-link-btn" onClick={() => saveEdit(meal.id)} disabled={savingEdit}>
                                {savingEdit ? '저장 중...' : '저장'}
                              </button>
                              <button className="diet-meal-cancel-btn" onClick={cancelEdit} disabled={savingEdit}>
                                취소
                              </button>
                            </div>
                          </div>
                        ) : (
                          <div className="diet-meal-inner">
                            <div style={{ flex: 1 }}>
                              <div className="diet-meal-title">{meal.menu_name}</div>
                              <div className="diet-meal-sub">{meal.kcal}kcal</div>
                            </div>
                            <div className="diet-meal-actions">
                              <button className="diet-meal-status" onClick={() => startEdit(meal)}>수정</button>
                              <button
                                className="diet-meal-delete"
                                onClick={() => handleDelete(meal.id)}
                                disabled={deletingId === meal.id}
                              >
                                {deletingId === meal.id ? '삭제 중...' : '삭제'}
                              </button>
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="mp-section-head">
            <div className="mp-section-title">오늘 하루 요약</div>
          </div>
          {todaySummary && (
            <div className="mp-stat-strip">
              <button className="mp-tag mp-tag-clickable" onClick={() => setNutrientModalOpen(true)}>
                <div className="mp-tag-label"><span>{SUMMARY_HEADLINE_FIELD.label}</span></div>
                <div className="mp-tag-inner">
                  <div className="mp-tag-value">{Math.round(todaySummary[SUMMARY_HEADLINE_FIELD.key])}</div>
                  <div className="mp-tag-unit">{SUMMARY_HEADLINE_FIELD.unit}</div>
                </div>
              </button>
            </div>
          )}
        </>
      ) : (
        <p className="pcard-desc" style={{ marginTop: 20 }}>로그인 후 식단을 기록할 수 있습니다.</p>
      )}

      {nutrientModalOpen && (
        <NutrientDetailModal summary={todaySummary} onClose={() => setNutrientModalOpen(false)} />
      )}

      {notFoundFoods && (
        <div className="modal-backdrop" onClick={() => setNotFoundFoods(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <button className="modal-close" onClick={() => setNotFoundFoods(null)} aria-label="닫기">×</button>
            <div className="modal-title">일부 음식을 찾지 못했어요</div>
            <div className="modal-sub">{notFoundFoods.join(', ')}</div>
            <p className="pcard-desc">
              표준 식품 DB에 없는 이름이에요. 다른 표현으로 다시 입력해주세요.
            </p>
            <button className="modal-btn" onClick={() => setNotFoundFoods(null)}>확인</button>
          </div>
        </div>
      )}
    </PageShell>
  )
}

export default DietPage

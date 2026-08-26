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

const SUMMARY_HEADLINE_FIELD = { key: 'totalCalories', unit: 'kcal' }
const DIET_DISCLAIMER_KEY = 'dietDisclaimerSeen'

/** food_items 컬럼은 DB에 저장된 JSON 문자열 그대로 내려오므로 파싱해서 씀. 형식이 깨져 있으면 빈 배열로 처리 */
function parseFoodItems(meal) {
  if (!meal.food_items) return []
  try {
    const parsed = typeof meal.food_items === 'string' ? JSON.parse(meal.food_items) : meal.food_items
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function DietPage() {
  const { user, logMeal, getTodayMeals, getTodayTotal, getMonthCalories, getNutrientTarget, updateMeal, updateMealItemAmount, deleteMeal } = useAuth()
  const [selectedDate, setSelectedDate] = useState(todayStr)
  const [mealType, setMealType] = useState('')
  const [meals, setMeals] = useState([])
  const [total, setTotal] = useState(null)
  const [nutrientTarget, setNutrientTarget] = useState(null)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [notice, setNotice] = useState('')
  const [notFoundInfo, setNotFoundInfo] = useState(null)
  const [editingId, setEditingId] = useState(null)
  const [editDraft, setEditDraft] = useState({ mealType: '', menuName: '', kcal: '' })
  const [savingEdit, setSavingEdit] = useState(false)
  const [deletingId, setDeletingId] = useState(null)
  const [nutrientModalOpen, setNutrientModalOpen] = useState(false)
  const [expandedMealId, setExpandedMealId] = useState(null)
  const [editingItem, setEditingItem] = useState(null)
  const [itemAmountDraft, setItemAmountDraft] = useState('')
  const [savingItem, setSavingItem] = useState(false)
  const [confirmDeleteId, setConfirmDeleteId] = useState(null)
  const [showDisclaimer, setShowDisclaimer] = useState(() => !localStorage.getItem(DIET_DISCLAIMER_KEY))

  const dismissDisclaimer = () => {
    localStorage.setItem(DIET_DISCLAIMER_KEY, '1')
    setShowDisclaimer(false)
  }

  const isToday = selectedDate === todayStr()

  const refresh = (date) => {
    getTodayMeals(date).then(setMeals).catch(() => {})
    getTodayTotal(date).then(setTotal).catch(() => {})
  }

  useEffect(() => {
    if (user) refresh(selectedDate)
    // 날짜를 바꿔 다른 날 기록을 보러 갈 때만 펼쳐둔 항목/편집 상태를 접음.
    // 그램 수 저장 직후의 refresh()에서는 패널이 접히지 않아야 하므로 여기서만 리셋.
    setExpandedMealId(null)
    setEditingItem(null)
  }, [user, selectedDate])

  useEffect(() => {
    if (user) getNutrientTarget().then(setNutrientTarget).catch(() => {})
  }, [user])

  const handleLog = () => {
    const text = input.trim()
    if (!text || loading) return

    setLoading(true)
    setNotice('')
    logMeal(text, mealType)
      .then((result) => {
        // 매칭된 항목만 저장되고, 실패한 항목은 notFoundFoods로 따로 안내됨 (부분 저장 가능)
        const saved = Boolean(result.menuNameSummary)
        if (saved) {
          refresh(selectedDate)
          setInput('')
        }
        if (result.notFoundFoods?.length) {
          setNotFoundInfo({ foods: result.notFoundFoods, saved })
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
      })
      .catch((e) => setNotice(e.message || '수정에 실패했어요'))
      .finally(() => setSavingEdit(false))
  }

  const toggleExpand = (mealId) => {
    setEditingItem(null)
    setExpandedMealId((prev) => (prev === mealId ? null : mealId))
  }

  const startEditItem = (mealId, index, currentAmountG) => {
    setEditingItem({ mealId, index })
    setItemAmountDraft(String(currentAmountG))
  }

  const cancelEditItem = () => setEditingItem(null)

  const saveEditItem = (mealId, index) => {
    const amount = Number(itemAmountDraft)
    if (!amount || amount <= 0) {
      setNotice('그램 수를 올바르게 입력해주세요')
      return
    }

    setSavingItem(true)
    setNotice('')
    updateMealItemAmount(mealId, index, amount)
      .then(() => {
        setEditingItem(null)
        refresh(selectedDate)
      })
      .catch((e) => setNotice(e.message || '그램 수 수정에 실패했어요'))
      .finally(() => setSavingItem(false))
  }

  const handleDelete = (id) => {
    setConfirmDeleteId(null)
    setDeletingId(id)
    deleteMeal(id)
      .then(() => {
        refresh(selectedDate)
      })
      .catch((e) => setNotice(e.message || '삭제에 실패했어요'))
      .finally(() => setDeletingId(null))
  }

  return (
    <PageShell>
      <div className="page-eyebrow-row">
        <div className="page-index-tag">Meal plan</div>
      </div>

      {user ? (
        <>
          <div className="diet-split">
            <div className="diet-col-left">
              <Calendar
                selected={selectedDate}
                onSelect={setSelectedDate}
                maxDateStr={todayStr()}
                getMonthCalories={getMonthCalories}
              />

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
              {total && (
                <div className="summary-row">
                  <span className="summary-row-label">총 섭취</span>
                  <div className="tag-strip">
                    <button className="tag tag-clickable" onClick={() => setNutrientModalOpen(true)}>
                      <div className="tag-inner">
                        <div className="tag-value">{Math.round(total[SUMMARY_HEADLINE_FIELD.key])}</div>
                        <div className="tag-unit">{SUMMARY_HEADLINE_FIELD.unit}</div>
                      </div>
                    </button>
                  </div>
                </div>
              )}

              <div className="section-head">
                <div className="section-title">기록한 메뉴</div>
              </div>


              <div className="diet-timeline" style={{ marginTop: 14 }}>
                {meals.length === 0 && (
                  <p className="pcard-desc">{isToday ? '오늘' : '이 날'} 기록된 식사가 없어요.</p>
                )}
                {meals.map((meal, index) => {
                  const foodItems = parseFoodItems(meal)
                  const expanded = expandedMealId === meal.id
                  // 같은 끼니 종류가 연달아 있으면 라벨은 처음 한 번만 보여주고, 그 뒤로는
                  // 라벨 없이 밑으로 이어붙는 느낌으로 표시 (백엔드가 끼니 종류별로 묶어서 정렬해줌)
                  const showLabel = index === 0 || meals[index - 1].meal_type !== meal.meal_type
                  return (
                  <div className="diet-row" key={meal.id}>
                    <div className="diet-time">
                      {showLabel ? (MEAL_TYPE_LABEL[meal.meal_type] ?? meal.meal_type) : ''}
                    </div>
                    <div className="diet-line">
                      <div className="diet-dot"></div>
                    </div>
                    <div className="diet-body">
                      <div className={`diet-meal${editingId === meal.id ? ' diet-meal-editing' : ''}`}>
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
                              <button className="link-btn" onClick={() => saveEdit(meal.id)} disabled={savingEdit}>
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
                                onClick={() => setConfirmDeleteId(meal.id)}
                                disabled={deletingId === meal.id}
                              >
                                {deletingId === meal.id ? '삭제 중...' : '삭제'}
                              </button>
                            </div>
                          </div>
                        )}
                      </div>

                      {foodItems.length > 0 && editingId !== meal.id && (
                        <>
                          <button className="diet-item-toggle" onClick={() => toggleExpand(meal.id)}>
                            {expanded ? '항목 접기' : `항목별 그램 보기 (${foodItems.length})`}
                          </button>

                          {expanded && (
                            <div className="diet-item-list">
                              {foodItems.map((it, idx) => {
                                const isEditingThis = editingItem?.mealId === meal.id && editingItem?.index === idx
                                return (
                                  <div className="diet-item-row" key={idx}>
                                    <span className="diet-item-name">{it.foodName}</span>
                                    {isEditingThis ? (
                                      <div className="diet-item-edit">
                                        <input
                                          className="diet-item-amount-input"
                                          type="number"
                                          value={itemAmountDraft}
                                          onChange={(e) => setItemAmountDraft(e.target.value)}
                                          disabled={savingItem}
                                          autoFocus
                                        />
                                        <span className="diet-item-unit">g</span>
                                        <button
                                          className="link-btn"
                                          onClick={() => saveEditItem(meal.id, idx)}
                                          disabled={savingItem}
                                        >
                                          {savingItem ? '저장 중...' : '저장'}
                                        </button>
                                        <button
                                          className="diet-meal-cancel-btn"
                                          onClick={cancelEditItem}
                                          disabled={savingItem}
                                        >
                                          취소
                                        </button>
                                      </div>
                                    ) : (
                                      <>
                                        <span className="diet-item-amount">{it.amountG}g</span>
                                        <span className="diet-item-kcal">{Math.round(it.calories)}kcal</span>
                                        <button
                                          className="diet-item-edit-btn"
                                          onClick={() => startEditItem(meal.id, idx, it.amountG)}
                                        >
                                          수정
                                        </button>
                                      </>
                                    )}
                                  </div>
                                )
                              })}
                            </div>
                          )}
                        </>
                      )}
                    </div>
                  </div>
                  )
                })}
              </div>
            </div>
          </div>
        </>
      ) : (
        <p className="pcard-desc" style={{ marginTop: 20 }}>로그인 후 식단을 기록할 수 있습니다.</p>
      )}

      {user && showDisclaimer && (
        <div className="modal-backdrop" onClick={dismissDisclaimer}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <button className="modal-close" onClick={dismissDisclaimer} aria-label="닫기">×</button>
            <div className="modal-title">기록 전에 알아두세요</div>
            <div className="modal-sub">
              여기 나오는 칼로리·영양성분은 식약처 표준 식품 데이터를 바탕으로 계산한 추정치예요.
              조리법이나 재료, 실제 먹은 양에 따라 실제 섭취량과는 차이가 있을 수 있으니 참고용으로 봐주세요.
            </div>
            <button className="modal-btn" onClick={dismissDisclaimer}>확인했어요</button>
          </div>
        </div>
      )}

      {nutrientModalOpen && (
        <NutrientDetailModal
          summary={total}
          target={nutrientTarget}
          onTargetChange={setNutrientTarget}
          title="총 섭취 영양소"
          onClose={() => setNutrientModalOpen(false)}
        />
      )}

      {confirmDeleteId != null && (
        <div className="modal-backdrop" onClick={() => setConfirmDeleteId(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <button className="modal-close" onClick={() => setConfirmDeleteId(null)} aria-label="닫기">×</button>
            <div className="modal-title">이 기록을 삭제할까요?</div>
            <div className="modal-btn-row">
              <button className="modal-btn-secondary" onClick={() => setConfirmDeleteId(null)}>취소</button>
              <button className="modal-btn" onClick={() => handleDelete(confirmDeleteId)}>삭제</button>
            </div>
          </div>
        </div>
      )}

      {notFoundInfo && (
        <div className="modal-backdrop" onClick={() => setNotFoundInfo(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <button className="modal-close" onClick={() => setNotFoundInfo(null)} aria-label="닫기">×</button>
            <div className="modal-title">
              {notFoundInfo.saved ? '나머지 일부 음식은 찾지 못했어요' : '음식을 찾지 못했어요'}
            </div>
            <div className="modal-sub">{notFoundInfo.foods.join(', ')}</div>
            <p className="pcard-desc">
              {notFoundInfo.saved
                ? '나머지 음식은 정상적으로 기록됐어요. 위 항목만 표준 식품 DB에 없어서 빠졌어요. 다른 표현으로 다시 입력해주세요.'
                : '표준 식품 DB에 없는 이름이에요. 다른 표현으로 다시 입력해주세요.'}
            </p>
            <button className="modal-btn" onClick={() => setNotFoundInfo(null)}>확인</button>
          </div>
        </div>
      )}
    </PageShell>
  )
}

export default DietPage

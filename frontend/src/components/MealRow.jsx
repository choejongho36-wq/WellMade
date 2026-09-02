import { useState } from 'react'
import { useAuth } from '../lib/auth.js'
import CandidateButtons from './CandidateButtons.jsx'
import { MEAL_TYPE_LABEL } from '../lib/mealTypes.js'

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

/**
 * 타임라인의 끼니 한 줄. 수정 중인 상태는 이 줄 안에서만 관리한다(다른 줄과 공유할 이유가 없음).
 *
 * 수정 경로 두 가지:
 *   - 끼니 수정(updateMeal): 끼니 종류/메뉴명/칼로리. 메뉴명을 바꾸면 서버가 새 음식으로 재계산
 *   - 항목 수정: 그램 수 변경(updateMealItemAmount) 또는 다른 음식으로 교체(resolveMealItemMatch)
 *
 * @param showLabel       같은 끼니가 연달아 있으면 라벨은 처음 한 번만 (백엔드가 끼니별로 묶어 정렬해줌)
 * @param expanded        "항목별 그램 보기"가 펼쳐졌는지 - 한 번에 하나만 열리게 부모가 관리
 * @param onChanged       저장/교체 후 부모가 목록을 다시 불러오도록
 * @param onRequestDelete 삭제 확인 모달을 부모가 띄우도록
 */
function MealRow({ meal, showLabel, expanded, onToggleExpand, onChanged, onError, onRequestDelete, deleting }) {
  const { updateMeal, updateMealItemAmount, resolveMealItemMatch } = useAuth()
  const [editing, setEditing] = useState(false)
  const [editDraft, setEditDraft] = useState({ mealType: '', menuName: '', kcal: '' })
  const [savingEdit, setSavingEdit] = useState(false)
  const [editingIndex, setEditingIndex] = useState(null)   // 그램을 수정 중인 항목
  const [amountDraft, setAmountDraft] = useState('')
  const [savingItem, setSavingItem] = useState(false)
  const [changingIndex, setChangingIndex] = useState(null) // 후보 교체 중인 항목

  const foodItems = parseFoodItems(meal)

  const startEdit = () => {
    setEditDraft({ mealType: meal.meal_type, menuName: meal.menu_name, kcal: meal.kcal })
    setEditing(true)
  }

  // 메뉴명을 바꾼 경우 서버가 그 이름으로 영양성분을 다시 조회해서 칼로리까지 새로 계산함
  // (이름이 그대로면 여기서 보낸 kcal이 그대로 저장됨)
  const saveEdit = () => {
    setSavingEdit(true)
    updateMeal(meal.id, { ...editDraft, kcal: Number(editDraft.kcal) || 0 })
      .then(() => {
        setEditing(false)
        onChanged()
      })
      .catch((e) => onError(e.message || '수정에 실패했어요'))
      .finally(() => setSavingEdit(false))
  }

  // 그램을 직접 지정하는 것이므로 인분수 환산 없이 그 값 그대로 재조회 + 끼니 합계 재계산
  const saveAmount = (index) => {
    const amount = Number(amountDraft)
    if (!amount || amount <= 0) {
      onError('그램 수를 올바르게 입력해주세요')
      return
    }

    setSavingItem(true)
    updateMealItemAmount(meal.id, index, amount)
      .then(() => {
        setEditingIndex(null)
        onChanged()
      })
      .catch((e) => onError(e.message || '그램 수 수정에 실패했어요'))
      .finally(() => setSavingItem(false))
  }

  // 후보를 고르면 그 음식으로 교체 - 서버가 이 선택을 기억해뒀다가 다음에 같은 표현이 나오면 자동 적용
  const pickCandidate = (index, candidate) => {
    setChangingIndex(index)
    resolveMealItemMatch(meal.id, index, candidate)
      .then(onChanged)
      .catch((e) => onError(e.message || '매칭 변경에 실패했어요'))
      .finally(() => setChangingIndex(null))
  }

  return (
    <div className="diet-row">
      <div className="diet-time">
        {showLabel ? (MEAL_TYPE_LABEL[meal.meal_type] ?? meal.meal_type) : ''}
      </div>
      <div className="diet-line">
        <div className="diet-dot"></div>
      </div>
      <div className="diet-body">
        <div className={`diet-meal${editing ? ' diet-meal-editing' : ''}`}>
          {editing ? (
            /* 수정 모드: 끼니 종류 / 메뉴명 / 칼로리 */
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
                min="0"
                value={editDraft.kcal}
                onChange={(e) => setEditDraft((d) => ({ ...d, kcal: e.target.value.replace(/-/g, '') }))}
                disabled={savingEdit}
              />
              {editDraft.menuName.trim() !== meal.menu_name && (
                <p className="diet-meal-edit-hint">
                  이름을 바꾸면 그 음식으로 칼로리·영양성분을 다시 계산해서 넣어요.
                  직접 입력한 칼로리와 기존 항목은 새 음식 하나로 대체돼요.
                </p>
              )}
              <div className="diet-meal-edit-actions">
                <button className="link-btn" onClick={saveEdit} disabled={savingEdit}>
                  {savingEdit ? '저장 중...' : '저장'}
                </button>
                <button className="diet-meal-cancel-btn" onClick={() => setEditing(false)} disabled={savingEdit}>
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
                <button className="diet-meal-status" onClick={startEdit}>수정</button>
                <button className="diet-meal-delete" onClick={onRequestDelete} disabled={deleting}>
                  {deleting ? '삭제 중...' : '삭제'}
                </button>
              </div>
            </div>
          )}
        </div>

        {/* 항목별 그램 보기 - 항목마다 그램 수정 / 매칭 경고 / 후보 교체 */}
        {foodItems.length > 0 && !editing && (
          <>
            <button className="diet-item-toggle" onClick={onToggleExpand}>
              {expanded
                ? '항목 접기'
                : `항목별 그램 보기 (${foodItems.length})${foodItems.some((it) => it.weightEstimated) ? ' · 그램 확인 필요' : ''}`}
            </button>

            {expanded && (
              <div className="diet-item-list">
                {foodItems.map((it, idx) => (
                  <div className="diet-item-row" key={idx}>
                    <div className="diet-item-row-main">
                      <span className="diet-item-name">
                        {it.foodName}
                        {it.servings > 1 && <span className="diet-item-servings">×{it.servings}</span>}
                        {it.matchTier === 'FUZZY' && (
                          <span className="diet-item-badge-fuzzy">비슷한 이름으로 추정</span>
                        )}
                      </span>
                      {editingIndex === idx ? (
                        <div className="diet-item-edit">
                          <input
                            className="diet-item-amount-input"
                            type="number"
                            min="0"
                            value={amountDraft}
                            onChange={(e) => setAmountDraft(e.target.value.replace(/-/g, ''))}
                            disabled={savingItem}
                            autoFocus
                          />
                          <span className="diet-item-unit">g</span>
                          <button className="link-btn" onClick={() => saveAmount(idx)} disabled={savingItem}>
                            {savingItem ? '저장 중...' : '저장'}
                          </button>
                          <button
                            className="diet-meal-cancel-btn"
                            onClick={() => setEditingIndex(null)}
                            disabled={savingItem}
                          >
                            취소
                          </button>
                        </div>
                      ) : (
                        <>
                          {!it.userEntered && <span className="diet-item-amount">{it.amountG}g</span>}
                          <span className="diet-item-kcal">{Math.round(it.calories)}kcal</span>
                          {/* 직접 입력한 항목은 DB에 없는 음식이라 그램 수로 재조회할 수 없음 */}
                          {!it.userEntered && (
                            <button
                              className="diet-item-edit-btn"
                              onClick={() => {
                                setEditingIndex(idx)
                                setAmountDraft(String(it.amountG))
                              }}
                            >
                              수정
                            </button>
                          )}
                        </>
                      )}
                    </div>

                    {it.matchTier === 'FUZZY' && (
                      <CandidateButtons
                        item={it}
                        onPick={(candidate) => pickCandidate(idx, candidate)}
                        changing={changingIndex === idx}
                      />
                    )}
                    {it.userEntered && (
                      <div className="diet-item-confidence diet-item-confidence-mid">
                        표준 식품 DB에 없어 직접 입력한 칼로리로 기록했어요 (영양소 미반영)
                      </div>
                    )}
                    {it.matchTier !== 'FUZZY' && it.weightEstimated && (
                      <div className="diet-item-confidence diet-item-confidence-mid">
                        표준 식품 DB에 1인분 중량이 없어 100g으로 넣었어요 -
                        실제로 드신 그램 수로 수정해주세요
                      </div>
                    )}
                    {it.matchTier !== 'FUZZY' && (
                      <details className="diet-item-confidence diet-item-confidence-mid">
                        <summary>다른 음식인가요? 후보 다시 보기</summary>
                        <CandidateButtons
                          item={it}
                          onPick={(candidate) => pickCandidate(idx, candidate)}
                          changing={changingIndex === idx}
                        />
                      </details>
                    )}
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

export default MealRow

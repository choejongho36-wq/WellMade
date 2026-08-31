import { useState } from 'react'
import { useAuth } from '../lib/auth.js'
import Modal from './Modal.jsx'
import CandidateButtons, { otherCandidates } from './CandidateButtons.jsx'
import { MEAL_TYPE_LABEL } from '../lib/mealTypes.js'

/** "2026-08-27" -> "8월 27일" */
function formatDateLabel(dateStr) {
  const [, month, day] = dateStr.split('-')
  return `${Number(month)}월 ${Number(day)}일`
}

/**
 * 식단 기록 입력 모달.
 *
 * 저장 후 모달을 닫는 경우와 열어두는 경우가 갈린다:
 *   - 전부 깔끔하게 인식됨        -> 닫는다
 *   - 매칭이 애매한 항목이 있음    -> logResult 패널을 띄워 그 자리에서 후보를 고르게 함
 *   - DB에 없는 음식이 있음        -> notFound 패널을 띄워 칼로리를 직접 적어 기록하게 함
 *
 * @param mealType 고른 끼니 - 모달을 닫아도 유지되도록 페이지가 들고 있는다
 * @param onSaved 저장/변경이 일어나 부모가 목록을 다시 불러와야 할 때
 * @param onError 실패 메시지 - 부모의 공용 알림 모달로 올려보낸다
 */
function DietLogModal({ selectedDate, isToday, mealType, onMealTypeChange, onClose, onSaved, onError }) {
  const { logMeal, logManualMeal, resolveMealItemMatch } = useAuth()
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [showTips, setShowTips] = useState(false)
  const [notFoundInfo, setNotFoundInfo] = useState(null) // DB에서 못 찾은 음식 + 직접 입력 UI
  const [logResult, setLogResult] = useState(null)       // 방금 기록한 결과 {mealId, items}
  const [manualKcal, setManualKcal] = useState({})       // 못 찾은 음식별 입력 중인 칼로리 {음식명: 값}
  const [manualSaving, setManualSaving] = useState('')   // 직접 기록 중인 음식명
  const [changingIndex, setChangingIndex] = useState(null)

  const close = () => {
    if (loading) return
    onClose()
  }

  const handleLog = () => {
    const text = input.trim()
    // 기록하기 버튼 disabled와 같은 조건을 여기서도 확인 - Enter로 들어오면 버튼 조건을 건너뛰기 때문.
    // 지난 날짜인데 끼니를 안 고르면 서버가 '현재 시각'으로 끼니를 추정해 엉뚱하게 저장된다
    if (!text || loading || (!isToday && !mealType)) return

    setLoading(true)
    setNotFoundInfo(null)
    setLogResult(null)
    logMeal(text, mealType, selectedDate)
      .then((result) => {
        // 매칭된 항목만 저장되고, 실패한 항목은 notFoundFoods로 따로 안내됨 (부분 저장 가능)
        const saved = Boolean(result.menuNameSummary)
        const notFound = result.notFoundFoods ?? []
        if (saved) {
          onSaved()
          // 저장된 부분은 입력창을 비운다 - 안 비우면 다시 기록하기를 눌렀을 때 중복 저장됨
          setInput('')
        }

        // 이름이 정확히 일치해도 엉뚱한 음식일 수 있어서(예: "토스트"는 DB에 음료류로도 있음),
        // 후보가 있는 항목이 하나라도 있으면 기록 직후 그 자리에서 바로 고를 수 있게 모달을 열어둔다
        const items = result.items ?? []
        const needsConfirm = items.some((it) => otherCandidates(it).length > 0)
        if (needsConfirm) {
          setLogResult({ mealId: result.mealId, items })
        }

        if (notFound.length) {
          setNotFoundInfo({ foods: notFound, saved })
        } else if (!needsConfirm) {
          onClose()
        }
      })
      .catch((e) => onError(e.message || '식단 기록에 실패했어요'))
      .finally(() => setLoading(false))
  }

  // Shift+Enter는 줄바꿈, Enter만 누르면 바로 기록
  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleLog()
    }
  }

  // 기록 직후 이 자리에서 다른 음식으로 교체 (타임라인의 후보 교체와 같은 API)
  const pickCandidate = (index, candidate) => {
    setChangingIndex(index)
    resolveMealItemMatch(logResult.mealId, index, candidate)
      .then((res) => {
        setLogResult((prev) => ({ ...prev, items: res.foodItems }))
        onSaved()
      })
      .catch((e) => onError(e.message || '매칭 변경에 실패했어요'))
      .finally(() => setChangingIndex(null))
  }

  // DB에 없는 음식을 칼로리만 직접 적어서 기록. 성공하면 그 음식만 안내 목록에서 뺀다
  const handleManualLog = (food) => {
    const kcal = Number(manualKcal[food])
    if (!kcal || kcal <= 0) {
      onError('칼로리를 숫자로 입력해주세요')
      return
    }

    setManualSaving(food)
    logManualMeal(food, kcal, mealType, selectedDate)
      .then(() => {
        onSaved()
        setManualKcal((prev) => {
          const next = { ...prev }
          delete next[food]
          return next
        })
        setNotFoundInfo((prev) => {
          if (!prev) return prev
          const foods = prev.foods.filter((f) => f !== food)
          return foods.length ? { ...prev, foods } : null
        })
      })
      .catch((e) => onError(e.message || '직접 기록에 실패했어요'))
      .finally(() => setManualSaving(''))
  }

  return (
    <Modal className="diet-log-modal" onClose={close}>
      <div className="diet-log-modal-head">
        <div className="modal-title">식단 기록하기</div>
        <button
          className="diet-log-help-btn"
          onClick={() => setShowTips((v) => !v)}
          aria-label="입력 안내"
          aria-expanded={showTips}
        >
          ?
        </button>
      </div>

      {showTips && (
        <ul className="diet-log-tips">
          <li><strong>몇 인분</strong>인지 같이 적어주세요. (예: 김치찌개 1인분, 밥 한공기)</li>
          <li><strong>그램 수</strong>를 적으면 그대로 계산돼요. (예: 닭가슴살 150g)</li>
          <li>양을 안 적으면 표준 식품 DB에 등록된 <strong>1인분 중량</strong>으로 계산해요.
            중량이 등록돼 있지 않은 음식(주로 생재료)은 100g으로 넣어두니, 기록 후 항목별 그램 수를 고치면 돼요.</li>
          <li>여러 음식은 한 번에 적어도 돼요. (예: 밥과 불고기 1인분랑 계란후라이 2개)</li>
          <li>표준 식품 DB에 없는 이름은 영양성분을 못 가져와요. 더 일반적인 메뉴 이름으로 바꾸거나,
            칼로리를 직접 적어서 그대로 기록할 수 있어요.</li>
        </ul>
      )}

      <div className="diet-log-form">
        {!isToday && (
          <p className="diet-log-date-notice">
            <strong>{formatDateLabel(selectedDate)}</strong>의 기록으로 저장돼요.
            끼니를 직접 골라주세요.
          </p>
        )}
        <select
          className="diet-mealtype-select"
          value={mealType}
          onChange={(e) => onMealTypeChange(e.target.value)}
          disabled={loading}
        >
          {/* 지난 날짜는 '자동'이 현재 시각으로 추정돼 엉뚱한 끼니가 되므로 직접 고르게 함 */}
          <option value="" disabled={!isToday}>
            {isToday ? '자동 (시간대로 추정)' : '시간 선택'}
          </option>
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

        {/* DB에서 못 찾은 음식 - 칼로리를 직접 적어 그대로 기록 */}
        {notFoundInfo && (
          <div className="diet-log-notfound">
            <strong>
              {notFoundInfo.saved ? '일부 음식은 기록하지 못했어요' : '음식을 찾지 못했어요'}
            </strong>
            <span>
              {notFoundInfo.saved
                ? '나머지는 정상적으로 기록됐어요. 아래 항목만 표준 식품 DB에 없어서 영양성분을 가져오지 못했어요.'
                : '표준 식품 DB에 없는 이름이에요. 더 일반적인 메뉴 이름으로 바꿔서 다시 기록하거나,'}
              {' '}칼로리를 직접 적어서 그대로 기록할 수 있어요. (영양소는 반영되지 않아요)
            </span>
            {notFoundInfo.foods.map((food) => (
              <div className="diet-manual-row" key={food}>
                <span className="diet-log-notfound-foods">{food}</span>
                <input
                  className="diet-item-amount-input"
                  type="number"
                  placeholder="칼로리"
                  value={manualKcal[food] ?? ''}
                  onChange={(e) => setManualKcal((prev) => ({ ...prev, [food]: e.target.value }))}
                  disabled={manualSaving === food}
                />
                <span className="diet-item-unit">kcal</span>
                <button
                  className="link-btn"
                  onClick={() => handleManualLog(food)}
                  disabled={manualSaving === food}
                >
                  {manualSaving === food ? '기록 중...' : '이대로 기록'}
                </button>
              </div>
            ))}
          </div>
        )}

        {/* 방금 기록한 항목 확인 - 잘못 인식됐으면 여기서 바로 다른 음식으로 교체 */}
        {logResult && (
          <div className="diet-log-result">
            <strong>기록했어요 · 인식된 음식이 맞는지 확인해주세요</strong>
            {logResult.items.map((it, idx) => (
              <div className="diet-log-result-item" key={idx}>
                <div className="diet-log-result-line">
                  <span className="diet-log-result-name">
                    {it.foodName}{it.servings > 1 && ` ×${it.servings}`}
                  </span>
                  <span className="diet-log-result-meta">
                    {it.amountG}g · {Math.round(it.calories)}kcal
                  </span>
                </div>
                {otherCandidates(it).length > 0 && (
                  <>
                    <span className="diet-log-result-hint">
                      {it.matchTier === 'FUZZY'
                        ? '⚠️ 비슷한 이름으로 추정했어요. 다른 음식이면 골라주세요'
                        : '다른 음식이면 골라주세요'}
                    </span>
                    <CandidateButtons
                      item={it}
                      onPick={(candidate) => pickCandidate(idx, candidate)}
                      changing={changingIndex === idx}
                    />
                  </>
                )}
              </div>
            ))}
            <button className="modal-btn" onClick={close}>확인</button>
          </div>
        )}

        <button
          className="chat-send-btn"
          onClick={handleLog}
          disabled={loading || !input.trim() || (!isToday && !mealType)}
        >
          {loading ? '기록 중...' : '기록하기'}
        </button>
      </div>
    </Modal>
  )
}

export default DietLogModal

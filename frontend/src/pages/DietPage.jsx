/**
 * 식단관리 페이지.
 *
 * 화면 구성:
 *   왼쪽 - 달력(날짜 선택, 날짜별 칼로리 표시) + "식단 기록하기" 버튼
 *   오른쪽 - 선택한 날짜의 총 섭취 칼로리 + 끼니별 타임라인
 *   모달 - 기록 입력(DietLogModal) / 영양소 상세 / 삭제 확인 / 첫 방문 안내 / 에러 알림
 *
 * 이 파일은 "선택한 날짜의 데이터를 불러오고, 어떤 모달을 띄울지" 만 관리한다.
 *   - 기록 입력 흐름(파싱 결과 확인, 후보 교체, 직접 입력) -> components/DietLogModal.jsx
 *   - 끼니 한 줄의 수정/삭제/항목 편집                     -> components/MealRow.jsx
 */
import { useCallback, useEffect, useState } from 'react'
import './DietPage.css'
import '../components/ChatDrawer.css'
import { useAuth } from '../lib/auth.js'
import { todayStr } from '../lib/dates.js'
import PageShell from '../components/PageShell.jsx'
import Calendar from '../components/Calendar.jsx'
import NutrientDetailModal from '../components/NutrientDetailModal.jsx'
import DietLogModal from '../components/DietLogModal.jsx'
import MealRow from '../components/MealRow.jsx'
import Modal from '../components/Modal.jsx'
import { MEAL_TYPE_LABEL } from '../lib/mealTypes.js'

/**
 * 같은 끼니에 여러 번 기록해도 화면에선 끼니 하나로 묶는다 - 점심을 세 번 나눠 적으면
 * 예전엔 "점심" 카드가 세 장 나왔다.
 *
 * 백엔드가 끼니 종류(아침->점심->저녁->간식)로 먼저 정렬해서 주므로 연속된 같은 종류를
 * 이어붙이면 그대로 끼니 그룹이 된다. 종류별로 훑지 않는 이유는, 그렇게 하면 목록에 없는
 * 끼니 코드가 들어왔을 때 그 기록이 화면에서 통째로 사라지기 때문.
 */
function groupByMealType(meals) {
  return meals.reduce((groups, meal) => {
    const last = groups[groups.length - 1]
    if (last && last.type === meal.meal_type) last.items.push(meal)
    else groups.push({ type: meal.meal_type, items: [meal] })
    return groups
  }, [])
}

const SUMMARY_HEADLINE_FIELD = { key: 'totalCalories', unit: 'kcal' }
const DIET_DISCLAIMER_KEY = 'dietDisclaimerSeen'

function DietPage() {
  const { user, getTodayMeals, getTodayTotal, getMonthCalories, getHolidays, getNutrientTarget, deleteMeal, getWorkoutMemo, saveWorkoutMemo, getWorkoutMemoMonth } = useAuth()

  // --- 화면 데이터 (선택 날짜 기준으로 서버에서 받아옴) ---
  const [selectedDate, setSelectedDate] = useState(todayStr)
  const [meals, setMeals] = useState([])
  const [total, setTotal] = useState(null)
  const [nutrientTarget, setNutrientTarget] = useState(null)

  // --- 열려 있는 모달 / 펼침 상태 ---
  const [logModalOpen, setLogModalOpen] = useState(false)
  const [mealType, setMealType] = useState('')            // 기록 모달에서 고른 끼니 (닫았다 열어도 유지)
  const [nutrientModalOpen, setNutrientModalOpen] = useState(false)
  const [expandedMealId, setExpandedMealId] = useState(null) // "항목별 그램 보기"를 펼친 끼니 (한 번에 하나만)
  const [confirmDeleteId, setConfirmDeleteId] = useState(null)
  const [deletingId, setDeletingId] = useState(null)
  const [notice, setNotice] = useState('')                   // 공용 에러 알림 모달 (모든 실패 메시지가 여기로)
  const [showDisclaimer, setShowDisclaimer] = useState(() => !localStorage.getItem(DIET_DISCLAIMER_KEY))

  // --- 메모 (선택 날짜 기준) ---
  const [memo, setMemo] = useState('')
  const [savedMemo, setSavedMemo] = useState('')   // 서버에 저장된 값 - 변경 여부 판단용
  const [memoSaving, setMemoSaving] = useState(false)
  const [memoSaved, setMemoSaved] = useState(false)   // 저장 직후 확인 표시
  const [memoEditing, setMemoEditing] = useState(false)  // 저장된 메모를 다시 고치는 중
  const [confirmMemoDelete, setConfirmMemoDelete] = useState(false)
  // 캘린더는 자기 안에서 월 데이터를 불러오므로, 저장 후 다시 읽게 하려면 신호가 필요하다.
  // 칼로리와 메모를 나눠 두는 이유: 하나로 합치면 식단을 저장할 때마다 메모 월 조회까지 같이 나간다.
  const [caloriesKey, setCaloriesKey] = useState(0)
  const [memoKey, setMemoKey] = useState(0)

  const isToday = selectedDate === todayStr()

  const dismissDisclaimer = () => {
    localStorage.setItem(DIET_DISCLAIMER_KEY, '1')
    setShowDisclaimer(false)
  }

  /* ===== 조회 ===== */

  /** 선택한 날짜의 끼니 목록 + 합계를 다시 불러옴 */
  const refresh = useCallback((date) => {
    // 조용히 실패하면 "저장이 안 됐나?" 하고 다시 누르게 되므로 실패는 알린다
    // (토큰 만료 401도 여기로 올라와 "다시 로그인해주세요"가 표시됨)
    Promise.all([getTodayMeals(date), getTodayTotal(date)])
      .then(([mealList, dailyTotal]) => {
        setMeals(mealList)
        setTotal(dailyTotal)
      })
      .catch((e) => setNotice(e.message || '식단 기록을 불러오지 못했어요'))
  }, [getTodayMeals, getTodayTotal])

  /**
   * 기록을 저장/수정/삭제한 뒤. 오른쪽 타임라인만 다시 읽으면 왼쪽 달력의 그날 숫자와 히트맵은
   * 옛 값 그대로 남는다(월을 넘겼다 돌아와야 맞았음). 달력 쪽도 같이 다시 읽게 신호를 올린다.
   * 날짜만 바꾸는 경우엔 월 합계가 달라질 리 없으므로 refresh()만 부른다.
   */
  const refreshAfterChange = useCallback((date) => {
    refresh(date)
    setCaloriesKey((k) => k + 1)
  }, [refresh])

  useEffect(() => {
    if (user) refresh(selectedDate)
    // 날짜를 바꿔 다른 날 기록을 보러 갈 때는 펼쳐둔 항목을 접는다
    // (저장 직후의 refresh()에서는 접히면 안 되므로 여기서만 리셋)
    setExpandedMealId(null)
  }, [user, selectedDate, refresh])

  useEffect(() => {
    if (user) getNutrientTarget().then(setNutrientTarget).catch(() => {})
  }, [user, getNutrientTarget])

  // 날짜를 바꾸면 그 날 메모를 다시 읽는다. 못 읽어도 화면을 막지 않고 빈 칸으로 둔다 -
  // 메모는 부가 기능이라 실패가 식단 기록까지 가리면 안 된다.
  useEffect(() => {
    if (!user) return
    let stale = false
    getWorkoutMemo(selectedDate)
      .then((content) => {
        if (stale) return
        setMemo(content)
        setSavedMemo(content)
        setMemoSaved(false)
        setMemoEditing(false)
      })
      .catch(() => {
        if (stale) return
        setMemo('')
        setSavedMemo('')
        setMemoEditing(false)
      })
    // 날짜를 빠르게 넘기면 늦게 온 응답이 최신 날짜의 메모를 덮어쓸 수 있어 무효화한다
    return () => { stale = true }
  }, [user, selectedDate, getWorkoutMemo])

  const handleSaveMemo = () => {
    setMemoSaving(true)
    saveWorkoutMemo(selectedDate, memo)
      .then((content) => {
        setMemo(content)
        setSavedMemo(content)
        setMemoSaved(true)
        setMemoEditing(false)   // 저장하면 아래 "기록된 메모" 카드로 돌아간다
        setMemoKey((k) => k + 1)   // 캘린더의 "메모 있는 날" 점을 바로 반영
      })
      .catch((e) => setNotice(e.message || '메모를 저장하지 못했어요'))
      .finally(() => setMemoSaving(false))
  }

  // 빈 내용으로 저장하면 서버가 그 날 메모를 지운다 (saveWorkoutMemo 주석 참고)
  const handleDeleteMemo = () => {
    setConfirmMemoDelete(false)
    setMemoSaving(true)
    saveWorkoutMemo(selectedDate, '')
      .then(() => {
        setMemo('')
        setSavedMemo('')
        setMemoSaved(false)
        setMemoEditing(false)
        setMemoKey((k) => k + 1)
      })
      .catch((e) => setNotice(e.message || '메모를 삭제하지 못했어요'))
      .finally(() => setMemoSaving(false))
  }

  /* ===== 삭제 ===== */

  const handleDelete = (id) => {
    setConfirmDeleteId(null)
    setDeletingId(id)
    deleteMeal(id)
      .then(() => refreshAfterChange(selectedDate))
      .catch((e) => setNotice(e.message || '삭제에 실패했어요'))
      .finally(() => setDeletingId(null))
  }

  return (
    <PageShell>
      <div className="page-eyebrow-row">
        <div className="page-index-tag">Calendar</div>
      </div>

      {user ? (
        <div className="diet-split">
          {/* ===== 왼쪽: 달력 + 기록 버튼 ===== */}
          <div className="diet-col-left">
            <Calendar
              selected={selectedDate}
              onSelect={setSelectedDate}
              maxDateStr={todayStr()}
              targetKcal={nutrientTarget?.kcal ?? 0}
              getMonthCalories={getMonthCalories}
              getHolidays={getHolidays}
              getWorkoutMemoMonth={getWorkoutMemoMonth}
              caloriesKey={caloriesKey}
              memoKey={memoKey}
            />

            {/* 운동이든 컨디션이든 자유롭게 적는 칸. 식단처럼 구조화하지 않은 이유는
                WorkoutMemo 엔티티 주석 참고.

                저장된 메모가 있으면 아래 "기록된 메모" 카드가 기본 화면이고, 거기서 수정을 눌러야
                이 입력칸이 열린다 - 예전엔 둘이 늘 같이 떠 있어서 같은 글이 두 번 보였다.
                (끼니 카드 MealRow의 읽기 -> 수정 흐름과 같은 방식) */}
            {(!savedMemo || memoEditing) && (
              <div className="diet-memo">
                <div className="diet-memo-spine"><span>MEMO</span></div>
                <div className="diet-memo-inner">
                  <div className="diet-memo-head">
                    <span className="diet-memo-title">{selectedDate.replace(/-/g, '.')}</span>
                    {memo !== savedMemo && <span className="diet-memo-dirty">저장 안 됨</span>}
                  </div>
                  <textarea
                    className="diet-memo-input"
                    value={memo}
                    maxLength={1000}
                    placeholder={`${isToday ? '오늘' : '이 날'} 기록을 남겨보세요. 예) 하체 - 스쿼트 60kg 5x5, 런닝 20분`}
                    onChange={(e) => { setMemo(e.target.value); setMemoSaved(false) }}
                  />
                  <div className="diet-memo-foot">
                    <span className="diet-memo-count">{memo.length}/1000</span>
                    <div className="diet-memo-actions">
                      {memoEditing && (
                        <button
                          className="diet-memo-cancel"
                          onClick={() => { setMemo(savedMemo); setMemoEditing(false) }}
                          disabled={memoSaving}
                        >
                          취소
                        </button>
                      )}
                      <button
                        className="diet-memo-save"
                        onClick={handleSaveMemo}
                        disabled={memoSaving || memo === savedMemo}
                      >
                        {memoSaving ? '저장 중...' : '저장'}
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* 지금 저장돼 있는 메모. 캘린더에서 점 찍힌 날을 누르면 그 날 메모가 여기 펼쳐진다 */}
            {savedMemo && !memoEditing && (
              <div className="diet-memo-view">
                <div className="diet-memo-spine"><span>MEMO</span></div>
                <div className="diet-memo-inner">
                  <div className="diet-memo-view-head">
                    <span>{selectedDate.replace(/-/g, '.')}</span>
                    <span className="diet-memo-view-actions">
                      <button className="diet-memo-edit" onClick={() => setMemoEditing(true)}>수정</button>
                      <button className="diet-memo-delete" onClick={() => setConfirmMemoDelete(true)} disabled={memoSaving}>
                        {memoSaving ? '삭제 중...' : '삭제'}
                      </button>
                    </span>
                  </div>
                  <p className="diet-memo-view-body">{savedMemo}</p>
                  {memoSaved && <p className="diet-memo-saved">저장됐어요 · 캘린더에 점으로 표시돼요</p>}
                </div>
              </div>
            )}
          </div>

          {/* ===== 오른쪽: 총 섭취 요약 + 끼니 타임라인 ===== */}
          <div className="diet-col-right">
            {/* 칼로리 태그를 누르면 영양소 상세 모달 */}
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
                <p className="diet-summary-note">
                  표준 식품 데이터로 계산한 추정치예요. 조리법·재료·실제 먹은 양에 따라
                  실제 섭취한 칼로리·영양소와 다를 수 있어요.
                </p>
              </div>
            )}

            <div className="section-head">
              <div className="section-title">기록한 메뉴</div>
            </div>

            <div className="diet-timeline" style={{ marginTop: 14 }}>
              {groupByMealType(meals).map((group, groupIndex) => (
                <section className="diet-group" key={`${group.type}-${groupIndex}`}>
                  <div className="diet-group-head">
                    <span className="diet-group-label">
                      <span>{MEAL_TYPE_LABEL[group.type] ?? group.type}</span>
                    </span>
                    <span className="diet-group-rule" />
                    {/* 기록이 하나뿐이면 카드에 적힌 칼로리와 같은 숫자라 굳이 두 번 쓰지 않는다 */}
                    {group.items.length > 1 && (
                      <span className="diet-group-total">
                        {group.items.reduce((sum, m) => sum + (m.kcal ?? 0), 0)}
                        <span className="diet-group-total-unit">kcal</span>
                      </span>
                    )}
                  </div>
                  <div className="diet-group-body">
                    {group.items.map((meal) => (
                      <MealRow
                        key={meal.id}
                        meal={meal}
                        expanded={expandedMealId === meal.id}
                        onToggleExpand={() => setExpandedMealId((prev) => (prev === meal.id ? null : meal.id))}
                        onChanged={() => refreshAfterChange(selectedDate)}
                        onError={setNotice}
                        onRequestDelete={() => setConfirmDeleteId(meal.id)}
                        deleting={deletingId === meal.id}
                      />
                    ))}
                  </div>
                </section>
              ))}
            </div>

            {/* 기록이 없는 날엔 이 버튼이 "기록된 식사가 없어요" 자리를 그대로 차지한다 */}
            <button className="diet-log-open-btn" onClick={() => setLogModalOpen(true)}>
              + {isToday ? '오늘' : '이 날'} 식단 기록하기
            </button>
          </div>
        </div>
      ) : (
        <p className="pcard-desc" style={{ marginTop: 20 }}>로그인 후 식단을 기록할 수 있습니다.</p>
      )}

      <footer className="diet-source-note">
        <strong>영양성분 데이터 출처</strong> · 식품의약품안전처 「전국통합식품영양성분정보 표준데이터」 (공공데이터포털)
        <br />
        식품의약품안전처, 농촌진흥청 국가표준식품성분표, 국립수산과학원 표준수산물성분표 자료를 통합한 공공데이터입니다.
        1인분 중량은 이 데이터의 &lsquo;식품중량&rsquo; 값을 그대로 사용하고, 그 값이 없는 음식은 100g 기준으로 넣은 뒤
        직접 수정할 수 있게 표시해요. 칼로리·영양성분은 100g(또는 100ml) 기준값을 섭취량 비율로 환산한 추정치예요.
      </footer>

      {user && logModalOpen && (
        <DietLogModal
          selectedDate={selectedDate}
          isToday={isToday}
          mealType={mealType}
          onMealTypeChange={setMealType}
          onClose={() => setLogModalOpen(false)}
          onSaved={() => refreshAfterChange(selectedDate)}
          onError={setNotice}
        />
      )}

      {/* 첫 방문 1회 안내 (localStorage로 다시 안 뜨게) */}
      {user && showDisclaimer && (
        <Modal onClose={dismissDisclaimer}>
          <div className="modal-title">기록 전에 알아두세요</div>
          <div className="modal-sub">
            여기 나오는 칼로리·영양성분은 식품의약품안전처 「전국통합식품영양성분정보 표준데이터」를 바탕으로 계산한 추정치예요.
            조리법이나 재료, 실제 먹은 양에 따라 실제 섭취량과는 차이가 있을 수 있으니 참고용으로 봐주세요.
            매칭이 불확실한 항목은 "항목별 그램 보기"를 펼치면 ⚠️ 표시와 함께 다른 후보를 고를 수 있어요.
          </div>
          <button className="modal-btn" onClick={dismissDisclaimer}>확인했어요</button>
        </Modal>
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
        <Modal onClose={() => setConfirmDeleteId(null)}>
          <div className="modal-title">이 기록을 삭제할까요?</div>
          <div className="modal-btn-row">
            <button className="modal-btn-secondary" onClick={() => setConfirmDeleteId(null)}>취소</button>
            <button className="modal-btn" onClick={() => handleDelete(confirmDeleteId)}>삭제</button>
          </div>
        </Modal>
      )}

      {confirmMemoDelete && (
        <Modal onClose={() => setConfirmMemoDelete(false)}>
          <div className="modal-title">{selectedDate.replace(/-/g, '.')} 메모를 삭제할까요?</div>
          <div className="modal-btn-row">
            <button className="modal-btn-secondary" onClick={() => setConfirmMemoDelete(false)}>취소</button>
            <button className="modal-btn" onClick={handleDeleteMemo}>삭제</button>
          </div>
        </Modal>
      )}

      {/* 공용 에러 알림 - 기록/수정/삭제 실패가 전부 여기로 모임 */}
      {notice && (
        <Modal onClose={() => setNotice('')}>
          <div className="modal-title">문제가 생겼어요</div>
          <div className="modal-sub">{notice}</div>
          <button className="modal-btn" onClick={() => setNotice('')}>확인</button>
        </Modal>
      )}
    </PageShell>
  )
}

export default DietPage

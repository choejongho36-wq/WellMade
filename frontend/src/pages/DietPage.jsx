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
import { useEffect, useState } from 'react'
import './DietPage.css'
import '../components/ChatDrawer.css'
import { useAuth } from '../lib/auth.js'
import PageShell from '../components/PageShell.jsx'
import Calendar from '../components/Calendar.jsx'
import NutrientDetailModal from '../components/NutrientDetailModal.jsx'
import DietLogModal from '../components/DietLogModal.jsx'
import MealRow from '../components/MealRow.jsx'
import Modal from '../components/Modal.jsx'

function todayStr() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

const SUMMARY_HEADLINE_FIELD = { key: 'totalCalories', unit: 'kcal' }
const DIET_DISCLAIMER_KEY = 'dietDisclaimerSeen'

function DietPage() {
  const { user, getTodayMeals, getTodayTotal, getMonthCalories, getHolidays, getNutrientTarget, deleteMeal } = useAuth()

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

  const isToday = selectedDate === todayStr()

  const dismissDisclaimer = () => {
    localStorage.setItem(DIET_DISCLAIMER_KEY, '1')
    setShowDisclaimer(false)
  }

  /* ===== 조회 ===== */

  /** 선택한 날짜의 끼니 목록 + 합계를 다시 불러옴. 저장/수정/삭제 후 매번 호출 */
  const refresh = (date) => {
    // 조용히 실패하면 "저장이 안 됐나?" 하고 다시 누르게 되므로 실패는 알린다
    // (토큰 만료 401도 여기로 올라와 "다시 로그인해주세요"가 표시됨)
    Promise.all([getTodayMeals(date), getTodayTotal(date)])
      .then(([mealList, dailyTotal]) => {
        setMeals(mealList)
        setTotal(dailyTotal)
      })
      .catch((e) => setNotice(e.message || '식단 기록을 불러오지 못했어요'))
  }

  useEffect(() => {
    if (user) refresh(selectedDate)
    // 날짜를 바꿔 다른 날 기록을 보러 갈 때는 펼쳐둔 항목을 접는다
    // (저장 직후의 refresh()에서는 접히면 안 되므로 여기서만 리셋)
    setExpandedMealId(null)
  }, [user, selectedDate])

  useEffect(() => {
    if (user) getNutrientTarget().then(setNutrientTarget).catch(() => {})
  }, [user])

  /* ===== 삭제 ===== */

  const handleDelete = (id) => {
    setConfirmDeleteId(null)
    setDeletingId(id)
    deleteMeal(id)
      .then(() => refresh(selectedDate))
      .catch((e) => setNotice(e.message || '삭제에 실패했어요'))
      .finally(() => setDeletingId(null))
  }

  return (
    <PageShell>
      <div className="page-eyebrow-row">
        <div className="page-index-tag">Meal plan</div>
      </div>

      {user ? (
        <div className="diet-split">
          {/* ===== 왼쪽: 달력 + 기록 버튼 ===== */}
          <div className="diet-col-left">
            <Calendar
              selected={selectedDate}
              onSelect={setSelectedDate}
              maxDateStr={todayStr()}
              getMonthCalories={getMonthCalories}
              getHolidays={getHolidays}
            />

            <button className="diet-log-open-btn" onClick={() => setLogModalOpen(true)}>
              + 식단 기록하기
            </button>
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
              {meals.length === 0 && (
                <p className="pcard-desc">{isToday ? '오늘' : '이 날'} 기록된 식사가 없어요.</p>
              )}
              {meals.map((meal, index) => (
                <MealRow
                  key={meal.id}
                  meal={meal}
                  // 같은 끼니 종류가 연달아 있으면 라벨은 처음 한 번만 (백엔드가 끼니별로 묶어 정렬해줌)
                  showLabel={index === 0 || meals[index - 1].meal_type !== meal.meal_type}
                  expanded={expandedMealId === meal.id}
                  onToggleExpand={() => setExpandedMealId((prev) => (prev === meal.id ? null : meal.id))}
                  onChanged={() => refresh(selectedDate)}
                  onError={setNotice}
                  onRequestDelete={() => setConfirmDeleteId(meal.id)}
                  deleting={deletingId === meal.id}
                />
              ))}
            </div>
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
          onSaved={() => refresh(selectedDate)}
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

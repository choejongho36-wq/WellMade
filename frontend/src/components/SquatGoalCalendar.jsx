import { useState } from 'react'
import { formatDateKey, todayDateKey } from '../lib/squatDailyStats.js'
import './SquatGoalCalendar.css'

/**
 * 이번 달 달력에 날짜별 운동/목표 달성 여부를 칸 밑 점으로 보여준다(초록 점: 목표 달성,
 * 노란 점: 운동은 했지만 목표 미달·목표 미설정, 점 없음: 운동 기록 없음) — 실시간 코칭 화면의
 * 달력 모달, 리포트 화면(ReportView), 운동 기록 페이지(ExerciseHistoryPage) 세 곳에서
 * 재사용한다(2026-09-09, SquatCoachingPage.jsx에서 분리 — 원래 그 파일 안에만 있었는데
 * 운동 기록 페이지가 카메라/MediaPipe 코드가 없는 가벼운 페이지라, 무거운
 * useSquatCoachingSession.js를 물고 있는 SquatCoachingPage.jsx를 통째로 import하지 않게
 * 하려고 뺐다).
 *
 * goal이 없으면(마이페이지에서 목표 미설정) 채움 없이 설정해 달라는 안내만 보여준다.
 * (2026-09-08 수정) goalTarget(숫자, 회수만) → goal(객체, { targetReps, targetSets }).
 * (2026-09-09 수정) "그날 목표를 채웠는지"를 완료한 세트 수(total_sets)만 보고 판단하면,
 * 세트 안에서 목표 횟수를 다 못 채워도 세트 개수만 채우면 달성으로 떴다 — 실제 채워야
 * 하는 건 그날 총 렙수(total_reps)가 목표 횟수×목표 세트수(targetReps × targetSets)
 * 이상인지다.
 *
 * onSelectDate가 주어지면(운동 기록 페이지) 날짜 칸이 버튼이 되어 클릭한 날짜를 부모에
 * 알리고, selectedDate와 같은 날짜엔 파란 테두리(오늘 표시용 빨간 테두리와는 별개)를
 * 보여준다. onSelectDate가 없으면(코칭 화면의 달력 모달·리포트 화면) 그냥 보여주기만
 * 한다 — 지금까지의 동작 그대로.
 */
function SquatGoalCalendar({ dailyStats, goal, onSelectDate, selectedDate }) {
  const [monthOffset, setMonthOffset] = useState(0)
  const base = new Date()
  const viewDate = new Date(base.getFullYear(), base.getMonth() + monthOffset, 1)
  const year = viewDate.getFullYear()
  const month = viewDate.getMonth()
  const firstWeekday = new Date(year, month, 1).getDay()
  const daysInMonth = new Date(year, month + 1, 0).getDate()
  const today = todayDateKey()

  const cells = []
  for (let i = 0; i < firstWeekday; i++) cells.push(null)
  for (let d = 1; d <= daysInMonth; d++) cells.push(d)

  const goalTotalReps = goal != null ? goal.targetReps * goal.targetSets : null
  const todayStat = dailyStats[today]
  const todayReps = todayStat?.total_reps ?? 0
  const todayGoalMet = goalTotalReps != null && todayReps >= goalTotalReps

  return (
    <div className="squat-calendar-card">
      <div className="squat-calendar-header">
        <button type="button" className="squat-calendar-nav" onClick={() => setMonthOffset((m) => m - 1)} aria-label="이전 달">
          ‹
        </button>
        <span className="squat-calendar-month">{year}년 {month + 1}월</span>
        <button type="button" className="squat-calendar-nav" onClick={() => setMonthOffset((m) => m + 1)} aria-label="다음 달">
          ›
        </button>
      </div>

      {goal != null ? (
        <div className="squat-calendar-today-goal">
          오늘 목표 {goal.targetReps}회 × {goal.targetSets}세트 중 <b>{Math.min(todayReps, goalTotalReps)}회</b> 완료
          {todayGoalMet ? ' · 달성! 🎉' : ` · ${Math.max(goalTotalReps - todayReps, 0)}회 남았어요`}
        </div>
      ) : (
        <div className="squat-calendar-today-goal squat-calendar-no-goal">
          마이페이지에서 스쿼트 목표 횟수·세트를 설정하면 달성한 날이 표시돼요.
        </div>
      )}

      <div className="squat-calendar-weekdays">
        {['일', '월', '화', '수', '목', '금', '토'].map((w) => (
          <span key={w}>{w}</span>
        ))}
      </div>
      <div className="squat-calendar-grid">
        {cells.map((d, i) => {
          if (d == null) return <span key={i} className="squat-calendar-cell squat-calendar-cell-empty" />
          const dateKey = formatDateKey(new Date(year, month, d))
          const stat = dailyStats[dateKey]
          // (2026-09-09 추가) 운동한 날은 칸 밑에 점으로 표시한다 — 초록 점: 그날 목표 달성,
          // 노란 점: 운동은 했지만 목표 미달(또는 목표 미설정), 점 없음: 그날 운동 기록 없음.
          // 달성 여부는 세트 개수가 아니라 그날 총 렙수 기준(goalTotalReps, 위 참고).
          const hasData = stat != null && stat.total_reps > 0
          const met = hasData && goalTotalReps != null && stat.total_reps >= goalTotalReps
          const isToday = dateKey === today
          const isSelected = onSelectDate != null && dateKey === selectedDate
          const title = stat ? `${dateKey} · ${stat.total_reps}회 ${stat.total_sets}세트` : dateKey
          const className = `squat-calendar-cell${isToday ? ' squat-calendar-cell-today' : ''}${isSelected ? ' squat-calendar-cell-selected' : ''}`
          const dot = hasData ? (
            <span className={`squat-calendar-dot ${met ? 'squat-calendar-dot-met' : 'squat-calendar-dot-attempt'}`} />
          ) : (
            <span className="squat-calendar-dot squat-calendar-dot-empty" />
          )
          const inner = (
            <>
              <span className="squat-calendar-day-num">{d}</span>
              {dot}
            </>
          )
          if (onSelectDate) {
            return (
              <button key={i} type="button" className={className} title={title} onClick={() => onSelectDate(dateKey)}>
                {inner}
              </button>
            )
          }
          return (
            <span key={i} className={className} title={title}>
              {inner}
            </span>
          )
        })}
      </div>
    </div>
  )
}

export default SquatGoalCalendar

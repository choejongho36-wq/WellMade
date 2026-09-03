import { useEffect, useState } from 'react'
import './Calendar.css'

const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토']

// 칸 배경 농도로 그날 섭취량을 보여준다(히트맵). 사용자 목표치가 아니라 고정 구간이라
// 목표를 설정하지 않았어도 한 달 패턴은 그대로 읽힌다.
function kcalLevel(kcal) {
  if (kcal == null) return null
  if (kcal < 1800) return 1
  if (kcal < 2000) return 2
  if (kcal < 2300) return 3
  return 4
}

function Calendar({ selected, onSelect, maxDateStr, getMonthCalories, getHolidays, getWorkoutMemoMonth, refreshKey }) {
  const [selYear, selMonth] = selected.split('-').map(Number)
  const [viewYear, setViewYear] = useState(selYear)
  const [viewMonth, setViewMonth] = useState(selMonth)
  const [caloriesByDate, setCaloriesByDate] = useState({})
  // 공휴일은 서버(HolidayService)가 공공데이터포털 특일 정보 API로 조회해서 내려줌 -
  // 예전처럼 연도별로 프론트에 하드코딩해두지 않아도 매년 자동으로 최신 상태가 됨.
  const [holidaysByDate, setHolidaysByDate] = useState({})
  // 메모가 있는 날 - 점으로 표시하고, 내용은 날짜를 고르면 캘린더 아래 카드에 펼쳐진다
  const [memosByDate, setMemosByDate] = useState({})

  useEffect(() => {
    if (!getMonthCalories) return
    getMonthCalories(viewYear, viewMonth).then(setCaloriesByDate).catch(() => setCaloriesByDate({}))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewYear, viewMonth, refreshKey])

  useEffect(() => {
    if (!getHolidays) return
    getHolidays(viewYear, viewMonth).then(setHolidaysByDate).catch(() => setHolidaysByDate({}))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewYear, viewMonth])

  useEffect(() => {
    if (!getWorkoutMemoMonth) return
    getWorkoutMemoMonth(viewYear, viewMonth).then(setMemosByDate).catch(() => setMemosByDate({}))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewYear, viewMonth, refreshKey])

  const todayStr = (() => {
    const d = new Date()
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  })()

  const goPrev = () => {
    if (viewMonth === 1) { setViewYear((y) => y - 1); setViewMonth(12) }
    else setViewMonth((m) => m - 1)
  }
  const goNext = () => {
    if (viewMonth === 12) { setViewYear((y) => y + 1); setViewMonth(1) }
    else setViewMonth((m) => m + 1)
  }

  const daysInMonth = new Date(viewYear, viewMonth, 0).getDate()
  const firstWeekday = new Date(viewYear, viewMonth - 1, 1).getDay()
  const cells = [...Array(firstWeekday).fill(null), ...Array(daysInMonth).keys()].map((v) => (v === null ? null : v + 1))

  const fmt = (day) => `${viewYear}-${String(viewMonth).padStart(2, '0')}-${String(day).padStart(2, '0')}`

  return (
    <div className="cal">
      <div className="cal-header">
        <div className="cal-title">
          {viewMonth}월<span className="cal-year">{viewYear}</span>
        </div>
        <div className="cal-nav-group">
          <button type="button" className="cal-nav" onClick={goPrev} aria-label="이전 달">‹</button>
          <button type="button" className="cal-nav" onClick={goNext} aria-label="다음 달">›</button>
        </div>
      </div>
      <div className="cal-weekdays">
        {WEEKDAYS.map((w) => (
          <div key={w} className="cal-weekday">{w}</div>
        ))}
      </div>
      <div className="cal-grid">
        {cells.map((day, i) => {
          if (day === null) return <div key={i} className="cal-cell empty" />
          const dateStr = fmt(day)
          const holidayName = holidaysByDate[dateStr]
          const kcal = caloriesByDate[dateStr]
          const memo = memosByDate[dateStr]
          const disabled = Boolean(maxDateStr) && dateStr > maxDateStr
          const classes = ['cal-cell']
          const level = kcalLevel(kcal)
          if (level) classes.push(`k${level}`)
          if (dateStr === selected) classes.push('selected')
          if (dateStr === todayStr) classes.push('today')
          if (holidayName) classes.push('holiday')
          return (
            <button
              key={i}
              type="button"
              className={classes.join(' ')}
              disabled={disabled}
              title={holidayName}
              onClick={() => onSelect(dateStr)}
            >
              <span className="cal-cell-top">
                <span className="cal-cell-day">{day}</span>
                {holidayName && <span className="cal-cell-holiday">{holidayName}</span>}
                {memo && <span className="cal-cell-memo" aria-label="메모 있음" />}
              </span>
              {kcal != null && <span className="cal-cell-kcal">{Math.round(kcal)}kcal</span>}
            </button>
          )
        })}
      </div>
    </div>
  )
}

export default Calendar

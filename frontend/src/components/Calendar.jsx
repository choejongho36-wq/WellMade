import { useEffect, useState } from 'react'
import './Calendar.css'

const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토']

// ponytail: 설날/추석/부처님오신날은 음력 기준이라 계산이 아니라 수기 목록으로 관리함.
// 새해가 오면 다음 해 날짜를 추가할 것 (공공데이터포털 특일 정보 API로 대체하면 갱신 필요 없음).
const KOREAN_HOLIDAYS = {
  '2025-01-01': '신정',
  '2025-01-28': '설날 연휴',
  '2025-01-29': '설날',
  '2025-01-30': '설날 연휴',
  '2025-03-01': '삼일절',
  '2025-03-03': '대체공휴일',
  '2025-05-01': '근로자의 날',
  '2025-05-05': '어린이날·부처님오신날',
  '2025-05-06': '대체공휴일',
  '2025-06-06': '현충일',
  '2025-08-15': '광복절',
  '2025-10-03': '개천절',
  '2025-10-05': '추석 연휴',
  '2025-10-06': '추석',
  '2025-10-07': '추석 연휴',
  '2025-10-08': '대체공휴일',
  '2025-10-09': '한글날',
  '2025-12-25': '크리스마스',

  '2026-01-01': '신정',
  '2026-02-16': '설날 연휴',
  '2026-02-17': '설날',
  '2026-02-18': '설날 연휴',
  '2026-03-01': '삼일절',
  '2026-03-02': '대체공휴일',
  '2026-05-01': '근로자의 날',
  '2026-05-05': '어린이날',
  '2026-05-24': '부처님오신날',
  '2026-05-25': '대체공휴일',
  '2026-06-03': '지방선거일',
  '2026-06-06': '현충일',
  '2026-07-17': '제헌절',
  '2026-08-15': '광복절',
  '2026-08-17': '대체공휴일',
  '2026-09-24': '추석 연휴',
  '2026-09-25': '추석',
  '2026-09-26': '추석 연휴',
  '2026-10-03': '개천절',
  '2026-10-05': '대체공휴일',
  '2026-10-09': '한글날',
  '2026-12-25': '크리스마스',

  '2027-01-01': '신정',
  '2027-02-07': '설날 연휴',
  '2027-02-08': '설날',
  '2027-02-09': '설날 연휴',
  '2027-03-01': '삼일절',
  '2027-05-01': '근로자의 날',
  '2027-05-05': '어린이날',
  '2027-05-13': '부처님오신날',
  '2027-06-06': '현충일',
  '2027-07-17': '제헌절',
  '2027-07-19': '대체공휴일',
  '2027-08-15': '광복절',
  '2027-08-16': '대체공휴일',
  '2027-09-14': '추석 연휴',
  '2027-09-15': '추석',
  '2027-09-16': '추석 연휴',
  '2027-10-03': '개천절',
  '2027-10-04': '대체공휴일',
  '2027-10-09': '한글날',
  '2027-10-11': '대체공휴일',
  '2027-12-25': '크리스마스',
  '2027-12-27': '대체공휴일',
}

function Calendar({ selected, onSelect, maxDateStr, getMonthCalories }) {
  const [selYear, selMonth] = selected.split('-').map(Number)
  const [viewYear, setViewYear] = useState(selYear)
  const [viewMonth, setViewMonth] = useState(selMonth)
  const [caloriesByDate, setCaloriesByDate] = useState({})

  useEffect(() => {
    if (!getMonthCalories) return
    getMonthCalories(viewYear, viewMonth).then(setCaloriesByDate).catch(() => setCaloriesByDate({}))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewYear, viewMonth])

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
        <button type="button" className="cal-nav" onClick={goPrev} aria-label="이전 달">‹</button>
        <div className="cal-title">{viewYear}년 {viewMonth}월</div>
        <button type="button" className="cal-nav" onClick={goNext} aria-label="다음 달">›</button>
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
          const holidayName = KOREAN_HOLIDAYS[dateStr]
          const kcal = caloriesByDate[dateStr]
          const disabled = Boolean(maxDateStr) && dateStr > maxDateStr
          const classes = ['cal-cell']
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

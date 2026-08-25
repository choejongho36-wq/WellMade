import { useState } from 'react'
import './Calendar.css'

const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토']

function Calendar({ selected, onSelect, maxDateStr }) {
  const [selYear, selMonth] = selected.split('-').map(Number)
  const [viewYear, setViewYear] = useState(selYear)
  const [viewMonth, setViewMonth] = useState(selMonth)

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
          const disabled = Boolean(maxDateStr) && dateStr > maxDateStr
          const classes = ['cal-cell']
          if (dateStr === selected) classes.push('selected')
          if (dateStr === todayStr) classes.push('today')
          return (
            <button
              key={i}
              type="button"
              className={classes.join(' ')}
              disabled={disabled}
              onClick={() => onSelect(dateStr)}
            >
              {day}
            </button>
          )
        })}
      </div>
    </div>
  )
}

export default Calendar

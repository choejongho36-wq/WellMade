import { useEffect, useState } from 'react'
import './Calendar.css'
import { todayStr as kstToday } from '../lib/dates.js'

const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토']

// 목표가 없을 때 쓰는 절대 구간. 성별·목표와 무관한 고정값이라 "많이 먹은 날"을 가려낼 뿐이지만,
// 목표를 설정하지 않았어도 한 달 패턴은 그대로 읽힌다.
const ABSOLUTE_LEVELS = [
  { max: 1800, level: 1, label: '1,800 미만' },
  { max: 2000, level: 2, label: '1,800~2,000' },
  { max: 2300, level: 3, label: '2,000~2,300' },
  { max: Infinity, level: 4, label: '2,300 이상' },
]

// 목표 섭취량이 있으면 목표 대비 비율로 색을 정한다. 절대 구간만 쓰면 1,500kcal이 목표인
// 감량 사용자에게 "목표를 지킨 날"이 제일 연하게 칠해져서 "적게 먹은 날"처럼 읽힌다.
const RATIO_LEVELS = [
  { max: 0.8, level: 1, label: '목표의 80% 미만' },
  { max: 1.1, level: 2, label: '목표 ±10%' },
  { max: 1.3, level: 3, label: '목표의 110~130%' },
  { max: Infinity, level: 4, label: '목표의 130% 초과' },
]

function levelsFor(targetKcal) {
  return targetKcal > 0 ? RATIO_LEVELS : ABSOLUTE_LEVELS
}

function kcalLevel(kcal, targetKcal) {
  if (kcal == null) return null
  const value = targetKcal > 0 ? kcal / targetKcal : kcal
  return levelsFor(targetKcal).find((step) => value < step.max).level
}

/**
 * 달력. 월 데이터(칼로리/공휴일/메모)는 이 컴포넌트가 직접 불러온다.
 *
 * caloriesKey / memoKey 는 부모가 "다시 읽어라"라고 알리는 신호다. 하나로 합쳐두면 식단을
 * 저장할 때마다 메모 월 조회까지 같이 나가므로 나눠서 받는다.
 */
function Calendar({
  selected, onSelect, maxDateStr, targetKcal,
  getMonthCalories, getHolidays, getWorkoutMemoMonth, caloriesKey, memoKey,
}) {
  const [selYear, selMonth] = selected.split('-').map(Number)
  const [viewYear, setViewYear] = useState(selYear)
  const [viewMonth, setViewMonth] = useState(selMonth)
  const [caloriesByDate, setCaloriesByDate] = useState({})
  // 공휴일은 서버(HolidayService)가 공공데이터포털 특일 정보 API로 조회해서 내려줌 -
  // 예전처럼 연도별로 프론트에 하드코딩해두지 않아도 매년 자동으로 최신 상태가 됨.
  const [holidaysByDate, setHolidaysByDate] = useState({})
  // 메모가 있는 날 - 점으로 표시하고, 값은 앞 30자 미리보기라 툴팁으로만 쓴다
  // (내용 전체는 날짜를 고르면 캘린더 아래 카드에 펼쳐진다)
  const [memosByDate, setMemosByDate] = useState({})
  // 월 데이터를 못 읽었을 때. 예전엔 조용히 빈 객체로 두어서, 토큰이 만료돼도 "기록이 없는 달"과
  // 구분이 안 됐다. 달력을 막을 정도는 아니라 한 줄 안내만 띄운다.
  const [loadError, setLoadError] = useState('')

  // 달을 빠르게 넘기면 늦게 온 8월 응답이 9월 화면을 덮어쓰므로, 지나간 요청은 무효화한다
  useEffect(() => {
    if (!getMonthCalories) return
    let stale = false
    getMonthCalories(viewYear, viewMonth)
      .then((data) => { if (!stale) setCaloriesByDate(data) })
      .catch((e) => {
        if (stale) return
        console.warn('월별 칼로리를 불러오지 못했습니다', e)
        setCaloriesByDate({})
        setLoadError(e.message || '달력 정보를 불러오지 못했어요')
      })
    return () => { stale = true }
  }, [getMonthCalories, viewYear, viewMonth, caloriesKey])

  useEffect(() => {
    if (!getHolidays) return
    let stale = false
    getHolidays(viewYear, viewMonth)
      .then((data) => { if (!stale) setHolidaysByDate(data) })
      // 공휴일은 없어도 달력이 정상 동작하므로 안내까지 띄우지는 않는다
      .catch((e) => { if (!stale) { console.warn('공휴일을 불러오지 못했습니다', e); setHolidaysByDate({}) } })
    return () => { stale = true }
  }, [getHolidays, viewYear, viewMonth])

  useEffect(() => {
    if (!getWorkoutMemoMonth) return
    let stale = false
    getWorkoutMemoMonth(viewYear, viewMonth)
      .then((data) => { if (!stale) setMemosByDate(data) })
      .catch((e) => {
        if (stale) return
        console.warn('월별 메모를 불러오지 못했습니다', e)
        setMemosByDate({})
        setLoadError(e.message || '달력 정보를 불러오지 못했어요')
      })
    return () => { stale = true }
  }, [getWorkoutMemoMonth, viewYear, viewMonth, memoKey])

  const todayStr = kstToday()
  const [todayYear, todayMonth] = todayStr.split('-').map(Number)

  const goPrev = () => {
    if (viewMonth === 1) { setViewYear((y) => y - 1); setViewMonth(12) }
    else setViewMonth((m) => m - 1)
  }
  const goNext = () => {
    if (viewMonth === 12) { setViewYear((y) => y + 1); setViewMonth(1) }
    else setViewMonth((m) => m + 1)
  }
  // 몇 달 뒤로 넘어가면 돌아올 방법이 화살표 연타뿐이었다. 보고 있는 달(viewYear/viewMonth)과
  // 선택 날짜(selected)는 따로 움직이므로 둘 다 되돌려야 한다.
  const goToday = () => {
    setViewYear(todayYear)
    setViewMonth(todayMonth)
    onSelect(todayStr)
  }
  const alreadyOnToday = viewYear === todayYear && viewMonth === todayMonth && selected === todayStr

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
          <button type="button" className="cal-today" onClick={goToday} disabled={alreadyOnToday}>오늘</button>
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
          const isSelected = dateStr === selected
          const isToday = dateStr === todayStr
          const disabled = Boolean(maxDateStr) && dateStr > maxDateStr
          const classes = ['cal-cell']
          const level = kcalLevel(kcal, targetKcal)
          if (level) classes.push(`k${level}`)
          if (isSelected) classes.push('selected')
          if (isToday) classes.push('today')
          if (holidayName) classes.push('holiday')

          // 칸 안의 숫자만 읽히면 스크린리더에서는 무슨 날인지 알 수 없어서 한 문장으로 만들어준다
          const label = [
            `${viewMonth}월 ${day}일`,
            holidayName,
            kcal != null ? `${Math.round(kcal).toLocaleString()}kcal` : null,
            memo ? '메모 있음' : null,
          ].filter(Boolean).join(', ')

          return (
            <button
              key={i}
              type="button"
              className={classes.join(' ')}
              disabled={disabled}
              title={[holidayName, memo].filter(Boolean).join(' · ') || undefined}
              aria-label={label}
              aria-pressed={isSelected}
              aria-current={isToday ? 'date' : undefined}
              onClick={() => onSelect(dateStr)}
            >
              <span className="cal-cell-top">
                <span className="cal-cell-day">{day}</span>
                {holidayName && <span className="cal-cell-holiday">{holidayName}</span>}
                {memo && <span className="cal-cell-memo" aria-hidden="true" />}
              </span>
              {kcal != null && <span className="cal-cell-kcal">{Math.round(kcal)}kcal</span>}
            </button>
          )
        })}
      </div>

      {/* 칸 색이 무슨 뜻인지 적어두지 않으면 알 방법이 없다. 목표가 있으면 기준 자체가
          목표 대비로 바뀌므로 무엇을 기준으로 칠했는지도 같이 밝힌다 */}
      <div className="cal-legend">
        <span className="cal-legend-title">{targetKcal > 0 ? '목표 대비' : '하루 섭취(kcal)'}</span>
        <span className="cal-legend-steps">
          {levelsFor(targetKcal).map((step) => (
            <span key={step.level} className="cal-legend-step">
              <span className={`cal-legend-chip k${step.level}`} aria-hidden="true" />
              {step.label}
            </span>
          ))}
        </span>
      </div>

      {loadError && <p className="cal-error">{loadError}</p>}
    </div>
  )
}

export default Calendar

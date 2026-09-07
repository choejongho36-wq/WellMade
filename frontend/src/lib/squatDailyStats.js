/**
 * 오늘 하루(그리고 날짜별) 스쿼트 운동 누적 기록 — 총 시간/총 횟수/이상 자세 감지 횟수를
 * 날짜별로 브라우저(localStorage)에 저장한다. 같은 날 여러 세션을 하면 값이 더해진다.
 *
 * 마이페이지에서 설정한 목표 횟수(exerciseGoals.js)와 비교해서, 스쿼트 코칭 리포트/실시간
 * 코칭 화면의 달력에 "그날 목표를 채웠는지"를 표시하는 데 쓴다.
 *
 * 날짜는 UTC(toISOString)가 아니라 브라우저의 로컬 날짜 기준이다 — UTC로 하면 자정 무렵
 * (한국시간 새벽 0~8시대)에 실제로는 "오늘"인데 "어제" 날짜로 잘못 기록되는 문제가 있다.
 */

const STORAGE_KEY = 'wellmade_squat_daily_stats'
const MAX_DAYS = 120 // 오래된 기록은 정리(용량 관리) — 최근 약 4개월치만 유지

// date를 "YYYY-MM-DD" 로컬 날짜 문자열로 바꾼다(달력 칸의 key로도 그대로 쓴다).
export function formatDateKey(date) {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

export function todayDateKey() {
  return formatDateKey(new Date())
}

function safeParseObject(json) {
  try {
    const parsed = JSON.parse(json)
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {}
  } catch {
    return {}
  }
}

// 저장된 날짜별 누적 기록을 { "2026-09-07": { total_reps, total_duration_sec, abnormal_reps }, ... } 형태로 반환한다.
export function loadSquatDailyStats() {
  try {
    return safeParseObject(localStorage.getItem(STORAGE_KEY) ?? '{}')
  } catch {
    return {}
  }
}

// date: "YYYY-MM-DD". delta는 이번 세션분만 넘기면 같은 날짜의 기존 값에 더해서 저장한다.
export function addSquatDailyStats(date, delta) {
  try {
    const all = loadSquatDailyStats()
    const prev = all[date] ?? { total_reps: 0, total_duration_sec: 0, abnormal_reps: 0 }
    all[date] = {
      total_reps: prev.total_reps + (delta.reps ?? 0),
      total_duration_sec: prev.total_duration_sec + (delta.durationSec ?? 0),
      abnormal_reps: prev.abnormal_reps + (delta.abnormalReps ?? 0),
    }
    const keys = Object.keys(all).sort()
    if (keys.length > MAX_DAYS) {
      for (const k of keys.slice(0, keys.length - MAX_DAYS)) delete all[k]
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(all))
    return all
  } catch {
    return loadSquatDailyStats()
  }
}

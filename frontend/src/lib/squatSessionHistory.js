/**
 * 스쿼트 세션 이력을 브라우저(localStorage)에 저장/조회한다.
 *
 * AI 서버는 세션 상태를 저장하지 않는 무상태 설계라(app/session/report.py 등 참고),
 * "직전 세션 대비" 비교와 "최근 세션 추이" 그래프에 쓸 이력은 프론트가 들고 있어야 한다.
 * 아직 로그인 연동 서버 저장소가 없어 우선 이 브라우저의 localStorage에만 남긴다 — 다른
 * 기기·브라우저에서는 이 이력이 보이지 않는다는 한계가 있다(추후 서버 저장으로 옮길 수 있다).
 *
 * (2026-09-09 확장) 엔트리 하나의 형태 — { date, normal_ratio, reps, durationSec, score,
 * avgMetrics: { knee_angle, hip_angle, shoulder_forward_lean_deg, knee_valgus_ratio },
 * issueCounts: { [part]: count }, mostFrequentIssuePart }. 이 확장 전에 저장된 옛 엔트리는
 * { date, normal_ratio }만 있을 수 있다 — 읽는 쪽(RecentSessionsList.sessionScore,
 * aggregateSessionsByDate 등)이 없는 필드는 안전한 기본값으로 처리한다.
 */

const STORAGE_KEY = 'wellmade_squat_session_history'
const MAX_ENTRIES = 20

function safeParseArray(json) {
  try {
    const parsed = JSON.parse(json)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

// 저장된 세션 이력을 오래된 순으로 반환한다(마지막 원소가 가장 최근) — { date, normal_ratio }.
export function loadSquatSessionHistory() {
  try {
    return safeParseArray(localStorage.getItem(STORAGE_KEY) ?? '[]')
  } catch {
    // localStorage 접근이 막힌 환경(프라이빗 모드 등) — 이력 없이 진행한다.
    return []
  }
}

// 세션 리포트 결과 하나를 이력에 추가하고, 최근 MAX_ENTRIES개만 남긴다.
export function appendSquatSessionHistory(entry) {
  try {
    const next = [...loadSquatSessionHistory(), entry].slice(-MAX_ENTRIES)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
    return next
  } catch {
    return loadSquatSessionHistory()
  }
}

// (2026-09-09 추가) 운동 기록 페이지(ExerciseHistoryPage)용 — 특정 날짜의 세션들을 하나로
// 합쳐서 그날의 "스쿼트 세션 요약"에 쓸 수 있게 만든다. 하루에 여러 세트(세션)를 했으면
// 점수·평균 지표는 재평균하고, 부위별 이상 횟수는 합산한다. 옛 형식(reps/score/avgMetrics/
// issueCounts 없음) 엔트리는 자동으로 빠지거나(점수·지표 평균에서 null 제외) 0으로
// 처리된다.
const POSE_METRIC_FIELDS = ['knee_angle', 'hip_angle', 'shoulder_forward_lean_deg', 'knee_valgus_ratio']

export function aggregateSessionsByDate(history, dateKey) {
  const entries = history.filter((h) => h.date === dateKey)

  const scores = entries.map((e) => e.score).filter((s) => s != null)
  const avgScore = scores.length > 0 ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length) : null

  const avgMetrics = {}
  for (const field of POSE_METRIC_FIELDS) {
    const vals = entries.map((e) => e.avgMetrics?.[field]).filter((v) => v != null)
    avgMetrics[field] = vals.length > 0 ? vals.reduce((a, b) => a + b, 0) / vals.length : null
  }

  const issueCounts = {}
  for (const entry of entries) {
    for (const [part, count] of Object.entries(entry.issueCounts ?? {})) {
      issueCounts[part] = (issueCounts[part] ?? 0) + count
    }
  }
  let mostFrequentIssuePart = null
  let maxCount = 0
  for (const [part, count] of Object.entries(issueCounts)) {
    if (count > maxCount) {
      maxCount = count
      mostFrequentIssuePart = part
    }
  }

  return { entries, avgScore, avgMetrics, issueCounts, mostFrequentIssuePart }
}

// 최근 세션 이력에서, 데이터가 있는 가장 최근 날짜를 반환한다(운동 기록 페이지가 처음
// 열렸을 때 기본으로 보여줄 날짜). 이력이 비어 있으면 null.
export function latestSessionDate(history) {
  return history.length > 0 ? history[history.length - 1].date : null
}

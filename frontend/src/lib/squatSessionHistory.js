/**
 * 스쿼트 세션 이력을 브라우저(localStorage)에 저장/조회한다.
 *
 * AI 서버는 세션 상태를 저장하지 않는 무상태 설계라(app/session/report.py 등 참고),
 * "직전 세션 대비" 비교와 "최근 세션 추이" 그래프에 쓸 이력은 프론트가 들고 있어야 한다.
 * 아직 로그인 연동 서버 저장소가 없어 우선 이 브라우저의 localStorage에만 남긴다 — 다른
 * 기기·브라우저에서는 이 이력이 보이지 않는다는 한계가 있다(추후 서버 저장으로 옮길 수 있다).
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

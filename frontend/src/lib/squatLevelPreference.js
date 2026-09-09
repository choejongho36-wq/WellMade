/**
 * 실시간 스쿼트 코칭의 초심자/숙련자 모드 선택을 기억한다(브라우저 localStorage).
 *
 * 원칙(2026-09-08, 사용자 요청): 처음 방문(저장된 값이 없음 = "처음 가입")이면 초심자
 * 모드가 기본값이다. 숙련자로 한 번이라도 바꾸면 그 선택이 계속 유지되고, 이후 다시
 * 바꾸면 그 값이 그대로 저장된다 — "기본은 초심자, 사용자가 명시적으로 바꾼 값만
 * 계속 기억한다"는 동작을 이 저장소 하나로 표현한다(저장된 값이 없으면 초심자,
 * 있으면 마지막으로 고른 값 그대로).
 *
 * exerciseGoals.js/squatDailyStats.js와 같은 패턴 — 로그인 계정과 별도로 이 브라우저
 * 안에서만 유지된다(계정 서버 동기화는 범위 밖).
 */

const STORAGE_KEY = 'wellmade_squat_level'
const DEFAULT_LEVEL = 'beginner'

export function loadSquatLevel() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw === 'expert' || raw === 'beginner' ? raw : DEFAULT_LEVEL
  } catch {
    return DEFAULT_LEVEL
  }
}

export function saveSquatLevel(level) {
  try {
    localStorage.setItem(STORAGE_KEY, level)
  } catch {
    // localStorage 접근 불가(프라이빗 모드 등) — 이번 세션에서만 적용되고 다음 방문엔
    // 다시 기본값(초심자)으로 시작한다. 저장 실패로 앱이 멈추면 안 되므로 조용히 무시.
  }
}

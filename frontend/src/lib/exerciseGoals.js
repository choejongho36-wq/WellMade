/**
 * 운동별(스쿼트 등) 하루 목표 횟수를 브라우저(localStorage)에 저장한다.
 *
 * 마이페이지의 "운동 목표 설정"에서 정하고, 스쿼트 코칭 화면의 달력이 이 값을 읽어
 * "오늘 목표를 채웠는지"를 표시하는 데 쓴다. 지금 실제로 판정·집계되는 운동은 스쿼트
 * (id: 'squat')뿐이라, 런지·플랭크는 목표만 저장될 뿐 리포트/달력에는 반영되지 않는다
 * (마이페이지에도 "개발중"으로 표시해 안내한다).
 *
 * configured는 마이페이지 "신체 정보 입력"과 같은 UI 패턴(설정 전엔 안내 카드, 설정 후엔
 * 이메일 아래 요약 줄)을 쓰기 위한 값이다 — 한 번도 저장한 적 없으면 false로 두고, 저장하고
 * 나면 true가 된다. 기본 스쿼트 목표(30회/일)는 configured와 무관하게 계속 달력 등에서
 * 쓰인다 — configured는 순수하게 "마이페이지에 뭘 보여줄지"만 결정한다.
 */

const STORAGE_KEY = 'wellmade_exercise_goals'

// 지금 앱에 있는(또는 예정된) 운동 목록 — 마이페이지 드롭다운/달력이 공유해서 쓴다.
export const EXERCISE_OPTIONS = [
  { id: 'squat', label: '스쿼트', devInProgress: false },
  { id: 'lunge', label: '런지', devInProgress: true },
  { id: 'plank', label: '플랭크', devInProgress: true },
]

const DEFAULT_STATE = {
  configured: false,
  goals: [{ id: 'squat', name: '스쿼트', targetReps: 30 }],
}

function safeParseState(json) {
  try {
    const parsed = JSON.parse(json)
    if (!parsed || typeof parsed !== 'object' || !Array.isArray(parsed.goals)) return null
    return { configured: Boolean(parsed.configured), goals: parsed.goals }
  } catch {
    return null
  }
}

export function loadExerciseGoalState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw == null) return DEFAULT_STATE
    return safeParseState(raw) ?? DEFAULT_STATE
  } catch {
    return DEFAULT_STATE
  }
}

// goals를 저장하고 configured를 true로 남긴다 — 마이페이지에서 "저장하기"를 눌렀을 때만 호출.
export function saveExerciseGoals(goals) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ configured: true, goals }))
  } catch {
    // localStorage 접근 실패는 조용히 무시 — 이번 변경만 반영이 안 될 뿐 화면은 정상 동작한다.
  }
}

export function getExerciseGoal(id) {
  return loadExerciseGoalState().goals.find((g) => g.id === id) ?? null
}

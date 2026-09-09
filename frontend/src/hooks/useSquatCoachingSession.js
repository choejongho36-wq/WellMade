/**
 * 실시간 스쿼트 코칭(측면 카메라)에 필요한 관절 각도/비율 계산 + 스켈레톤 오버레이 그리기.
 *
 * 계산 공식은 예전 ai/app/pose/angles.py를 JS로 그대로 이식한 것이고(현재는 "무거운 연산은
 * 클라이언트, 서버는 경량 수치만 비교" 원칙에 따라 프론트가 담당), pages/MlTestPage.jsx의
 * 검증된 구현(실제 사진/영상으로 확인된 임계값·보정 포함)을 그대로 따른다 — 두 곳에서 같은
 * 공식이 따로 어긋나지 않도록, 새로 만드는 페이지(SquatCoachingPage)는 이 모듈을 공유해서
 * 쓴다.
 *
 * (2026-09-07 변경) 측면 세션이 끝나면 화면에 "정면으로 마주보고 서주세요" 안내가 나오고,
 * 이어서 정면 단계(무릎모임 knee_valgus_ratio 판정)로 자동 전환된다 — 순차 전환(카메라는
 * 그대로, 사람이 돌아서는 방식)이라 카메라 재요청 없이 같은 세션 안에서 이어진다. AI-06
 * 요청에는 이번이 측면/정면 어느 쪽인지 view 필드로 실어 보낸다(schemas.py의
 * CoachingFrameRequest.view, coaching/realtime.py의 judge_realtime_coaching 참고).
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { usePoseLandmarker } from './usePoseLandmarker.js'
import { buildFrontMetrics, buildSideMetrics, drawSkeleton, isFullBodyVisible, STANDING_KNEE_ANGLE_MIN } from '../lib/squatPose.js'
import { AI_BASE } from '../lib/aiApi.js'
import { appendSquatSessionHistory, loadSquatSessionHistory } from '../lib/squatSessionHistory.js'
import { addSquatDailyStats, loadSquatDailyStats, todayDateKey } from '../lib/squatDailyStats.js'
import { getExerciseGoal } from '../lib/exerciseGoals.js'


const SAMPLE_INTERVAL_MS = 200 // 실시간 판독 주기 — 대려 5fps
const BUFFER_MAX = 30 // 롤돁링 버퍼 최대 프레임 수(약 6초 분량)
const MIN_USABLE_FRAMES = 3 // 서버(judge_realtime_coaching)의 MIN_FRAMES와 동일한 기준
const JUDGE_WINDOW = 6 // 매 호출마뤌에서 서버에 보낼 "최근 N프레솄" 걬간 크기
const END_CHECK_EVERY_N_FRAMES = 10 // 종료 판정 은 프레임마다 부를 필요 없어 약 2초마다만 확인

// (2026-09-09 추가) metricsSumRef/frontMetricsSumRef에 값 하나를 누적한다 — null/NaN이면
// 건너뛴다(예: 깊게 안 앉은 프레임의 gated 지표, 정면 단계를 안 해서 애초에 안 불리는 경우).
function accumulateMetric(ref, key, value) {
  if (value == null || Number.isNaN(value)) return
  const cur = ref.current[key] ?? { sum: 0, count: 0 }
  ref.current[key] = { sum: cur.sum + value, count: cur.count + 1 }
}

// 누적된 값의 평균을 반환한다 — 한 번도 누적 안 됐으면(count 0) null(계산 불가를 뜻함,
// ExerciseHistoryPage가 이 null을 보고 "정면 촬영이 있어야 계산돼요" 같은 안내로 대체한다).
function averageMetric(ref, key) {
  const cur = ref.current[key]
  return cur && cur.count > 0 ? cur.sum / cur.count : null
}

// (2026-09-08 추가) 서버(judge_realtime_coaching)는 무상태라 "이 렙 안에서 몇 번째 노출인지"를
// 스스로 알 수 없어, 렙당 노출 횟수 제한은 프론트에서 담당한다 — 실사용 테스트에서 렙 하나
// 안에 "움직임이 불안정합니다"가 4~6번씩 반복된다는 피드백에 따른 조치(서버 쪽 임곗값도 함께
// 완화했다, ai/app/coaching/realtime.py의 JITTER_STD_THRESHOLD_DEG 주석 참고).
const MOVEMENT_WARNING_MAX_PER_REP = 2

// TTS가 상태 변화에 밀려서 대기열에 쌓였다가 늦게 줄줄이 나오는 것을 막기 위한 속도 제한 —
// 문구가 바뀌었을 때 최소 이만큼(초), 같은 문구가 계속될 때는 이만큼(초) 간격을 두고서만
// 실제로 speak()가 새 발화를 시작한다(speak() 함수 참고).
const MIN_NEW_PHRASE_GAP_SEC = 4
const REPEAT_SAME_TEXT_GAP_SEC = 5
const FULL_BODY_WARNING_REPEAT_SEC = 10 // 전신 미노출 경고는 다른 문구보다 더 길게 쉬었다가 반복
// 발목/뒤꿈치/발끝 visibility 값이 프레임마다(200ms) 경계값 근처에서 미세하게 흔들릴 수
// 있어서, 연속 이 프레임 수 이상 같은 판정이 나올 때만 경고를 켜거나 끈다(히스테리시스) —
// 안 그러면 '전신이 나오게...'와 다른 안내 문구가 매 프레임 번갈아 반복될 수 있다.
const FULL_BODY_STREAK_THRESHOLD = 3

// 전신이 보이고 자세도 정상인데 아직 앉지 않은(서 있는) 상태일 때, "인식 중"이라는 애매한
// 문구 대신 스쿼트 방법을 한 단계씩 순서대로 안내한다(문구 출처: 프로젝트 문서
// "스쿼트 세션 진행 코칭 문구"). 한 단계를 말하고(speak) → 조용히 쉬었다가(pause) →
// 다음 단계로 넘어가는 것을 반복하고, 5단계까지 다 돌면 조금 더 길게 쉬었다가 1단계부터
// 다시 시작한다.
const STANDING_STEPS = [
  '발은 어깨너비로 벌리고, 발끝은 살짝 바깥쪽을 향하게 해주세요.',
  '무릎은 발끝과 같은 방향으로 굽혀주세요.',
  '허벅지가 바닥과 평행해질 때까지 천천히 앉아주세요.',
  '앉을 때 무릎이 발끝보다 너무 앞으로 나가지 않게 해주세요.',
  '허리는 곧게 편 상태를 유지해주세요.',
]
const STANDING_STEP_SPEAK_SEC = 4 // 한 단계를 안내하는 시간
const STANDING_STEP_PAUSE_SEC = 4 // 다음 단계로 넘어가기 전 조용히 쉬는 시간
const STANDING_STEP_LOOP_PAUSE_SEC = 7 // 5단계까지 다 돌고 1단계로 돌아가기 전 조금 더 길게 쉬는 시간

// 정면 단계에서는 knee_angle/hip_angle(측면 전용 값)을 판정에 쓰지 않지만, AI-06 요청
// 스키마상 필수 필드라 자리만 채우는 더미 값이 필요하다 — "서 있는" 값(180도 근처)을
// 넣어둔다(백엔드가 view="front"일 때 이 필드를 아예 읽지 않으므로 실제 값은 무관하다).
const FRONT_PLACEHOLDER_ANGLE = 180

async function postJson(path, body) {
  const res = await fetch(`${AI_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

// 코칭 로그에 붙이는 경과 시간(세션 시작 기준) — "0:07" 형태.
function formatElapsed(sec) {
  const total = Math.max(0, Math.round(sec))
  const m = Math.floor(total / 60)
  const s = total % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

export function useSquatCoachingSession() {
  const { detectPose } = usePoseLandmarker()

  const [phase, setPhase] = useState('idle') // idle | active | report
  const [cameraError, setCameraError] = useState('')
  const [judgeResult, setJudgeResult] = useState(null)
  const [judgeError, setJudgeError] = useState('')
  const [bufferCount, setBufferCount] = useState(0)
  const [endCheck, setEndCheck] = useState(null)
  const [sessionReport, setSessionReport] = useState(null)
  const [recordedVideoUrl, setRecordedVideoUrl] = useState(null) // 방금 운동 다시보기용 재생 URL
  const [reportLoading, setReportLoading] = useState(false)
  const [reportError, setReportError] = useState('')
  const [ttsEnabled, setTtsEnabled] = useState(true)
  const [fullBodyWarning, setFullBodyWarning] = useState(false)
  const [sessionStage, setSessionStage] = useState('side') // 'side' | 'front'
  const [coachingLog, setCoachingLog] = useState([]) // { id, time, text, state: 'ok'|'warn' }
  // 최근 세션 이력(날짜별 정상 비율) — 마이페이지 등 서버 저장소가 아직 없어 이 브라우저의
  // localStorage에만 남긴다(squatSessionHistory.js 참고). 리포트 화면의 세션 추이 그래프에 쓴다.
  const [sessionHistory, setSessionHistory] = useState(() => loadSquatSessionHistory().slice(-5))
  // 이번 세션에서 완료된 렙별 요약 — 리포트 화면의 렙 타임라인에 쓴다(repHistoryRef 참고).
  const [repHistory, setRepHistory] = useState([])
  // 오늘(그리고 과거) 날짜별 누적 기록 — 총 시간/총 횟수/이상 자세 감지(squatDailyStats.js
  // 참고). 실시간 코칭 화면의 달력 버튼과 리포트 화면의 '오늘' 요약 모두 이 값을 쓴다.
  const [dailyStats, setDailyStats] = useState(() => loadSquatDailyStats())
  // 마이페이지에서 설정한 스쿼트 하루 목표 횟수 — 없으면 null(달력이 목표 달성 표시를 생략한다).
  // (2026-09-08 수정) 숫자(targetReps)만 들고 있던 것을 목표 객체 전체({ targetReps,
  // targetSets }) 로 바꿨다 — 세트 목표(targetSets)가 추가되면서 반복 횟수 하나만으로는
  // 진행률을 표현할 수 없어졌다(exerciseGoals.js 참고).
  // (2026-09-09) setSquatGoal도 같이 내보낸다 — 코칭 페이지의 "카메라 켜고 시작하기"
  // 버튼에서 목표 미설정 시 모달을 띄워 그 자리에서 저장하면, 이 세션이 곧바로 새
  // 목표를 쓰도록 갱신해야 한다(원래는 마운트 시 한 번만 읽고 끝이었다).
  const [squatGoal, setSquatGoal] = useState(() => getExerciseGoal('squat'))

  const videoRef = useRef(null)
  const canvasRef = useRef(null)
  const streamRef = useRef(null)
  // "방금 운동 다시보기" 녹화용 - 좌표 판정용 프레임 샘플링(framesRef)과는 별개로,
  // 세션 진행 중 화면 영상 자체를 MediaRecorder로 녹화해 브라우저에만 잠깐 들고 있는다.
  // 서버로는 절대 자동 전송하지 않고, 신고 눌렀을 때만 이 Blob을 신고 데이터로 보낸다.
  const mediaRecorderRef = useRef(null)
  const recordedChunksRef = useRef([])
  const recordedVideoUrlRef = useRef(null)
  const recordedVideoBlobRef = useRef(null)
  const intervalRef = useRef(null)
  const offscreenRef = useRef(null)
  const startTimeRef = useRef(0)
  const tickRunningRef = useRef(false)
  const framesRef = useRef([]) // { timestamp, landmarks, metrics }
  // 전신 노출 판정 히스테리시스용 — 연속으로 같은 판정이 몇 프레임째인지(FULL_BODY_STREAK_THRESHOLD 참고)
  const fullBodyMissingStreakRef = useRef(0)
  const fullBodyVisibleStreakRef = useRef(0)
  const judgmentHistoryRef = useRef([]) // { timestamp, is_normal, issues[] }
  const frontJudgmentHistoryRef = useRef([]) // 정면 단계 전용 { timestamp, is_normal, issues[] }
  // 최종 리포트 전용 — 무릎 각도가 STANDING_KNEE_ANGLE_MIN 아래로 내려갔다가 다시 그
  // 이상으로 올라오는 구간 하나를 "스쿼트 1회"로 세서 쌓는다(측면 단계만 — 정면은 무릎
  // 각도를 잴 수 없어 이번에는 반복 횟수에 포함하지 않는다). 세션 자동 종료 판단에 쓰는
  // judgmentHistoryRef(프레임 단위)와는 용도가 달라 별도로 둔다.
  const repHistoryRef = useRef([]) // { timestamp, is_normal, issues } — 완료된 렙별 요약
  // (2026-09-09 추가) 세션 전체 평균 자세 지표 누적 — 운동 기록 페이지의 "자세 분석 결과"에
  // 쓴다. framesRef는 최근 6초짜리 롤링 버퍼라 세션 전체 평균을 못 내서 따로 둔다.
  // { [field]: { sum, count } } 형태 — 측면 단계 지표(무릎각도/엉덩이각도/상체기울기)는
  // metricsSumRef에, 정면 단계에서만 계산되는 무릎모임(knee_valgus_ratio)은
  // frontMetricsSumRef에 따로 쌓는다(정면 단계를 안 한 세션은 frontMetricsSumRef가 계속
  // 비어 있어 평균이 null로 나온다 — ExerciseHistoryPage가 "정면 촬영이 있어야 계산돼요"
  // 안내로 대체하는 신호로 쓴다).
  const metricsSumRef = useRef({})
  const frontMetricsSumRef = useRef({})
  const repInProgressRef = useRef(false) // 지금 "내려간(깊게 앉은)" 구간 안에 있는지
  const repHadIssueRef = useRef(false) // 이번 렙 동안 이상 자세가 한 번이라도 있었는지
  const repIssuesRef = useRef([]) // 이번 렙 동안 발생한 이슈 부위(중복 제거)
  const movementWarningCountRef = useRef(0) // 이번 렙 동안 'movement' 이슈가 노출된 횟수(MOVEMENT_WARNING_MAX_PER_REP 캡용)
  const lastSpokenRef = useRef('')
  const lastSpokenAtRef = useRef(-Infinity)
  const lastLoggedRef = useRef('')
  const standingStepIndexRef = useRef(0) // 지금 안내 중인 단계(0~4)
  const standingPhaseRef = useRef(null) // null(미시작) | 'speak' | 'pause'
  const standingPhaseStartRef = useRef(0) // 현재 phase가 시작된 시각(세션 경과 초)

  // timestamp: 세션 경과 초(tick의 timestamp). force가 true면 속도 제한 없이 바로 말한다
  // (세션 종료 리포트 요약처럼 한 번만 나가는 멘트용).
  const speak = useCallback(
    (text, timestamp, opts = {}) => {
      const { force = false, repeatGapSec } = opts
      if (!ttsEnabled || !text) return
      if (!('speechSynthesis' in window)) return
      if (!force) {
        const now = timestamp ?? 0
        const isSameText = text === lastSpokenRef.current
        const gapNeeded = isSameText ? (repeatGapSec ?? REPEAT_SAME_TEXT_GAP_SEC) : MIN_NEW_PHRASE_GAP_SEC
        if (now - lastSpokenAtRef.current < gapNeeded) return
      }
      lastSpokenRef.current = text
      lastSpokenAtRef.current = timestamp ?? lastSpokenAtRef.current
      const utterance = new SpeechSynthesisUtterance(text)
      utterance.lang = 'ko-KR'
      // 재생 중인 멘트를 cancel()로 끊고 새로 시작하면 상태가 자주 바뀔 때 문장이 중간에
      // 잘려서 들린다 — cancel 없이 speak만 호출해 지금 멘트가 끝난 뒤 다음 멘트가
      // 대기열에서 이어서 재생되게 한다(대기열 자체가 밀리는 건 위 속도 제한으로 막는다).
      window.speechSynthesis.speak(utterance)
    },
    [ttsEnabled],
  )

  // (2026-09-08 추가) result.issues 중 실제로 안내할 첫 항목을 고른다 — 'movement'
  // (움직임 불안정) 이슈는 이번 렙에서 이미 MOVEMENT_WARNING_MAX_PER_REP번 노출됐으면
  // 건너뛰고 그 다음 이슈(있으면)를 대신 쓴다. 전부 movement뿐이고 캡을 넘겼으면 undefined를
  // 반환해 "조용히 넘어가기"가 되도록 한다(호출부에서 빈 문자열로 처리).
  const pickPrimaryIssue = (issues) => {
    const filtered = (issues ?? []).filter(
      (issue) => issue.part !== 'movement' || movementWarningCountRef.current < MOVEMENT_WARNING_MAX_PER_REP,
    )
    const primary = filtered[0]
    if (primary?.part === 'movement') movementWarningCountRef.current += 1
    return primary
  }

  // is_normal이어도 무릎이 STANDING_KNEE_ANGLE_MIN 이상(=서 있는 상태)이면 서버가 하단
  // 자세 검사 자체를 건너뛴 것뿐이라 "정상"이 나온다 — 실제로 앉은 상태(isDeepHold)일 때만
  // "지금 자세를 유지하세요"를 내보낸다.
  const coachingText = (result, isDeepHold) =>
    result.is_normal
      ? (isDeepHold ? '좋아요, 지금 자세를 유지하세요' : '')
      : (pickPrimaryIssue(result.issues)?.message ?? '')

  // 화면 배지/음성 안내와 같은 문구를 오른쪽 코칭 로그에도 시간과 함께 쌓는다 — 같은
  // 문구가 연달아 반복될 때는(예: 계속 같은 이슈) 매번 쌓지 않고 처음 한 번만 기록한다.
  const logMessage = useCallback((text, state, elapsedSec) => {
    if (!text || text === lastLoggedRef.current) return
    lastLoggedRef.current = text
    setCoachingLog((log) =>
      [{ id: `${Date.now()}-${Math.random()}`, time: formatElapsed(elapsedSec), text, state }, ...log].slice(0, 50),
    )
  }, [])

  const stopCameraTracks = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop())
      streamRef.current = null
    }
    if (videoRef.current) videoRef.current.srcObject = null
  }, [])

  const stop = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
    // 녹화 중이면 먼저 MediaRecorder를 멈춰 마지막 데이터를 flush한 뒤에 카메라 트랙을
    // 정지한다 - 순서를 바꾸면(트랙 먼저 정지) 녹화가 중간에 잘릴 수 있다.
    const recorder = mediaRecorderRef.current
    if (recorder && recorder.state !== 'inactive') {
      recorder.onstop = () => {
        const blob = new Blob(recordedChunksRef.current, { type: recorder.mimeType || 'video/webm' })
        recordedChunksRef.current = []
        if (recordedVideoUrlRef.current) URL.revokeObjectURL(recordedVideoUrlRef.current)
        const url = URL.createObjectURL(blob)
        recordedVideoUrlRef.current = url
        recordedVideoBlobRef.current = blob
        setRecordedVideoUrl(url)
        stopCameraTracks()
      }
      recorder.stop()
    } else {
      stopCameraTracks()
    }
    // 대기열에 밀려 있던 코칭 멘트가 세션 종료 후까지 계속 재생되는 것을 막는다.
    if ('speechSynthesis' in window) window.speechSynthesis.cancel()
  }, [stopCameraTracks])

  const requestReport = useCallback(
    async (endReason) => {
      // 측면 단계 이력 + 정면 단계 이력을 시간순으로 합쳐서 세션 시간을 계산한다(프레임
      // 단위라 촘촘해서 "언제 끝났는지"를 정확히 반영한다).
      // (2026-09-09 수정) 판정이 한 번도 안 찍혔다고(전신이 한 번도 안 잡혔거나, 시작하자마자
      // 바로 종료) 조용히 idle로 돌아가지 않는다 — 그러면 사용자 입장에선 "종료" 버튼을
      // 눌러도 아무 반응이 없는 것처럼 보인다. 0회짜리 리포트라도 보여준다(백엔드
      // frame_history도 빈 리스트를 받아들이게 함께 고쳤다, ai/app/schemas.py 참고).
      const tickHistory = [...judgmentHistoryRef.current, ...frontJudgmentHistoryRef.current]
      // 리포트에 보낼 frame_history는 "몇 프레임 찍혔는지"가 아니라 "몇 렙(반복) 했는지"를
      // 반영해야 한다 — 완료된 렙이 하나라도 있으면 그걸 쓰고, 없으면(세션이 너무 짧아
      // 한 렙도 못 채운 경우 등) 기존처럼 프레임 단위로라도 보여준다.
      const repHistory = repHistoryRef.current
      const reportFrames = repHistory.length > 0 ? repHistory : tickHistory
      const sessionDurationSec = tickHistory.length > 0 ? tickHistory[tickHistory.length - 1].timestamp : 0
      setReportLoading(true)
      setReportError('')
      setSessionReport(null)
      try {
        const data = await postJson('/ai/session/report', {
          session_id: `squat-${Date.now()}`,
          frame_history: reportFrames.map(({ timestamp, is_normal, issues }) => ({
            timestamp,
            is_normal,
            issues: (issues ?? []).map((issue) => ({ part: issue.part })),
          })),
          session_duration_sec: sessionDurationSec,
          previous_sessions: loadSquatSessionHistory()
            .slice(-5)
            .map((h) => ({ session_date: h.date, normal_ratio: h.normal_ratio })),
          end_reason: endReason === 'user_requested' ? 'user_requested' : 'target_sustained',
        })
        setRepHistory(repHistoryRef.current)

        // (2026-09-09 재구성) 점수 = 렙(반복)마다 배점을 쌓는 방식으로 바꿨다 — 목표
        // 횟수(마이페이지에서 설정한 targetReps)가 있으면 렙 1개당 배점을 100 ÷ 목표
        // 횟수로 두고, 없으면 100 ÷ 실제 수행 렙수로 대신한다. 정상 렙은 배점 그대로,
        // 이상이 감지된 렙은 배점의 절반만(0점이 되지 않게 절반만 깎는 식) 가점해서 다
        // 더하고, 목표보다 많이 해도 100점을 넘지 않게 자른다. 완료한 렙이 하나도 없으면
        // (세션이 너무 짧아 렙 단위로 매길 게 없는 경우) 정상 자세 비율만으로 매긴다 —
        // 아예 아무 판정도 없었으면(0회) 자연히 0점이 된다.
        // 운동 기록 페이지의 "최근 세션"/세트별 기록 점수 배지에 쓴다.
        const goalReps = squatGoal?.targetReps
        const completedReps = repHistoryRef.current
        let score
        if (completedReps.length > 0) {
          const scoreDenom = goalReps > 0 ? goalReps : completedReps.length
          const perRepPoints = 100 / scoreDenom
          const rawScore = completedReps.reduce(
            (sum, rep) => sum + (rep.is_normal ? perRepPoints : perRepPoints * 0.5),
            0,
          )
          score = Math.min(100, Math.round(rawScore))
        } else {
          score = Math.round(data.normal_ratio * 100)
        }
        // (2026-09-09) 리포트 화면 제목 옆에 오늘 점수를 바로 보여줄 수 있게, sessionReport
        // 자체에 score를 실어서 담는다 — 원래 data를 그대로 setSessionReport 했었는데,
        // 점수 계산이 그 뒤에 있어서 순서를 이렇게 옮겼다.
        setSessionReport({ ...data, score })

        // 세션 내내 누적한 평균 자세 지표 — 운동 기록 페이지의 "자세 분석 결과"에 쓴다.
        // knee_valgus_ratio는 정면 단계를 안 했으면 null로 남는다(averageMetric 참고).
        const avgMetrics = {
          knee_angle: averageMetric(metricsSumRef, 'knee_angle'),
          hip_angle: averageMetric(metricsSumRef, 'hip_angle'),
          shoulder_forward_lean_deg: averageMetric(metricsSumRef, 'shoulder_forward_lean_deg'),
          heel_lift_ratio: averageMetric(metricsSumRef, 'heel_lift_ratio'),
          knee_over_toe_ratio: averageMetric(metricsSumRef, 'knee_over_toe_ratio'),
          knee_valgus_ratio: averageMetric(frontMetricsSumRef, 'knee_valgus_ratio'),
        }

        // 이번 세션 결과를 이력에 남겨서 다음 세션의 "지난 세션 대비", 추이 그래프, 그리고
        // 운동 기록 페이지의 최근 세션 리스트·세트별 기록·자세 분석 결과에 쓴다.
        const updatedHistory = appendSquatSessionHistory({
          date: new Date().toISOString().slice(0, 10),
          normal_ratio: data.normal_ratio,
          reps: data.total_reps,
          durationSec: data.session_duration_sec,
          score,
          avgMetrics,
          issueCounts: data.issue_counts_by_part ?? {},
          mostFrequentIssuePart: data.most_frequent_issue_part ?? null,
        })
        setSessionHistory(updatedHistory.slice(-5))
        // 오늘 날짜에 이번 세션의 시간/횟수/이상 자세 감지를 더해서 누적한다 — 리포트의
        // '오늘' 요약과 달력의 목표 달성 표시가 이 값을 쓴다.
        const updatedDaily = addSquatDailyStats(todayDateKey(), {
          reps: data.total_reps,
          durationSec: data.session_duration_sec,
          abnormalReps: data.abnormal_reps,
          sets: 1, // (2026-09-08 추가) 세션 1회 종료 = 세트 1회 완료로 집계한다.
        })
        setDailyStats(updatedDaily)
        speak(data.summary_message, null, { force: true })
      } catch (err) {
        setReportError(`AI 서버 연결 실패: ${err.message}`)
      } finally {
        setReportLoading(false)
      }
    },
    [speak, squatGoal],
  )

  const endSession = useCallback(
    (reason) => {
      stop()
      setPhase('report')
      requestReport(reason)
    },
    [stop, requestReport],
  )

  const checkSessionEnd = useCallback(async (history, userRequested) => {
    if (history.length === 0) return null
    try {
      const data = await postJson('/ai/session/end-check', {
        judgment_history: history.map(({ timestamp, is_normal }) => ({ timestamp, is_normal })),
        user_requested_end: userRequested,
      })
      setEndCheck(data)
      return data
    } catch {
      return null // 종료 판정 실패는 세션을 막지 않는다 — 사용자가 직접 끝낼 수 있다.
    }
  }, [])

  // 측면 세션이 끝나면(checkSessionEnd의 target_sustained) 카메라는 그대로 두고 사람만
  // 돌아서는 정면 단계로 전환한다 — 안내 두 문구를 순서대로 재생/기록하고, 정면 판정에
  // 필요한 상태를 리셋한다.
  const transitionToFront = useCallback(
    (timestamp) => {
      standingPhaseRef.current = null
      standingStepIndexRef.current = 0
      framesRef.current = []
      setBufferCount(0)
      setFullBodyWarning(false)
      fullBodyMissingStreakRef.current = 0
      fullBodyVisibleStreakRef.current = 0
      setEndCheck(null)
      frontJudgmentHistoryRef.current = []
      lastSpokenRef.current = ''
      lastSpokenAtRef.current = -Infinity
      lastLoggedRef.current = ''
      setSessionStage('front')

      const turnMessage = '이번에는 정면으로 카메라를 마주보고 서주십시오.'
      const focusMessage = '이번 정면 코칭은 무릎모임을 중점적으로 판단합니다.'
      speak(turnMessage, timestamp, { force: true })
      logMessage(turnMessage, 'ok', timestamp)
      speak(focusMessage, timestamp, { force: true })
      logMessage(focusMessage, 'ok', timestamp)
    },
    [speak, logMessage],
  )

  const tick = useCallback(async () => {
    if (tickRunningRef.current) return
    tickRunningRef.current = true
    try {
      const video = videoRef.current
      if (!video || video.readyState < 2) return

      if (!offscreenRef.current) offscreenRef.current = document.createElement('canvas')
      const offscreen = offscreenRef.current
      const scale = video.videoWidth > 480 ? 480 / video.videoWidth : 1
      const w = Math.round(video.videoWidth * scale)
      const h = Math.round(video.videoHeight * scale)
      if (offscreen.width !== w || offscreen.height !== h) {
        offscreen.width = w
        offscreen.height = h
      }
      offscreen.getContext('2d').drawImage(video, 0, 0, w, h)

      const landmarks = await detectPose(offscreen)
      if (!landmarks) return

      const timestamp = (performance.now() - startTimeRef.current) / 1000

      // 발목/뒤꿈치/발끝이 화면 밖으로 잘려 전신이 안 보이면, 그 프레임은 판정에 쓰지 않고
      // 뒤로 물러나 달라고 안내한다 — 안 그러면 발 기준 지표가 다 신뢰할 수 없는 채로
      // "정상 자세"까지 나올 수 있다. visibility 값 자체가 프레임마다 흔들릴 수 있어(특히
      // 발끝 쪽), 연속 FULL_BODY_STREAK_THRESHOLD 프레임 이상 같은 판정일 때만 경고를
      // 켜거나 끈다 — 그 사이(흔들리는 구간)에는 상태를 바꾸지 않고 조용히 건너뛴다.
      const bodyVisibleNow = isFullBodyVisible(landmarks)
      if (bodyVisibleNow) {
        fullBodyVisibleStreakRef.current += 1
        fullBodyMissingStreakRef.current = 0
      } else {
        fullBodyMissingStreakRef.current += 1
        fullBodyVisibleStreakRef.current = 0
      }

      if (fullBodyMissingStreakRef.current >= FULL_BODY_STREAK_THRESHOLD) {
        setFullBodyWarning(true)
        standingPhaseRef.current = null
        const warningText = '전신이 나오게 뒤로 한 발짝 물러나주세요.'
        speak(warningText, timestamp, { repeatGapSec: FULL_BODY_WARNING_REPEAT_SEC })
        logMessage(warningText, 'warn', timestamp)
        return
      }
      if (fullBodyVisibleStreakRef.current < FULL_BODY_STREAK_THRESHOLD) {
        return
      }
      setFullBodyWarning(false)

      const isFront = sessionStage === 'front'
      const metrics = isFront ? buildFrontMetrics(landmarks) : buildSideMetrics(landmarks)
      const frame = { timestamp, landmarks, metrics }
      const next = [...framesRef.current, frame].slice(-BUFFER_MAX)
      framesRef.current = next
      setBufferCount(next.length)
      drawSkeleton(video, canvasRef.current, landmarks)

      if (next.length < MIN_USABLE_FRAMES) return

      const start = Math.max(0, next.length - JUDGE_WINDOW)
      const angle_history = next.slice(start).map((f) => ({
        timestamp: f.timestamp,
        // 정면 단계는 knee_angle/hip_angle이 필수 필드 자리채움용일 뿐이라(위 상수 참고)
        // f.metrics보다 먼저 펼쳐서, 혹시 모를 실제 값이 있으면 그쪽이 우선하게 한다.
        ...(isFront ? { knee_angle: FRONT_PLACEHOLDER_ANGLE, hip_angle: FRONT_PLACEHOLDER_ANGLE } : {}),
        ...f.metrics,
      }))

      try {
        const result = await postJson('/ai/coaching/frame', { angle_history, view: sessionStage })
        setJudgeError('')

        if (isFront) {
          frontJudgmentHistoryRef.current = [
            ...frontJudgmentHistoryRef.current,
            { timestamp, is_normal: result.is_normal, issues: result.issues ?? [] },
          ]
          // (2026-09-09 추가) 무릎모임은 정면 전용 지표라(gated 아님, ANALYSIS_METRICS 참고)
          // 매 프레임 누적한다 — 정면 단계를 아예 안 하면 이 누적 자체가 안 일어나 세션
          // 리포트의 좌우 균형 평균이 null로 남는다.
          accumulateMetric(frontMetricsSumRef, 'knee_valgus_ratio', frame.metrics.knee_valgus_ratio)
          const text = result.is_normal
            ? '좋아요, 무릎이 발끝 방향을 잘 유지하고 있어요'
            : (result.issues?.[0]?.message ?? '무릎 모임을 확인해주세요')
          speak(text, timestamp)
          logMessage(text, result.is_normal ? 'ok' : 'warn', timestamp)
          setJudgeResult({ ...result, view: 'front', isDeepHold: false, standingStepText: '' })

          if (frontJudgmentHistoryRef.current.length % END_CHECK_EVERY_N_FRAMES === 0) {
            const end = await checkSessionEnd(frontJudgmentHistoryRef.current, false)
            if (end?.should_end) endSession(end.reason)
          }
        } else {
          judgmentHistoryRef.current = [
            ...judgmentHistoryRef.current,
            { timestamp, is_normal: result.is_normal, issues: result.issues ?? [] },
          ]
          const isDeepHold = frame.metrics.knee_angle < STANDING_KNEE_ANGLE_MIN

          // (2026-09-09 추가) 무릎각도/엉덩이각도/발뒤꿈치 들림/무릎-발끝 거리는 깊게
          // 앉았을 때만 의미 있는 값이라(gated:true, ANALYSIS_METRICS 참고) isDeepHold일
          // 때만 누적하고, 상체 기울기(시선·목)는 앉은 정도와 무관하게 항상 확인 가능한
          // 값이라(gated:false) 매 프레임 누적한다.
          accumulateMetric(metricsSumRef, 'knee_angle', isDeepHold ? frame.metrics.knee_angle : null)
          accumulateMetric(metricsSumRef, 'hip_angle', isDeepHold ? frame.metrics.hip_angle : null)
          accumulateMetric(metricsSumRef, 'shoulder_forward_lean_deg', frame.metrics.shoulder_forward_lean_deg)
          accumulateMetric(metricsSumRef, 'heel_lift_ratio', isDeepHold ? frame.metrics.heel_lift_ratio : null)
          accumulateMetric(metricsSumRef, 'knee_over_toe_ratio', isDeepHold ? frame.metrics.knee_over_toe_ratio : null)

          // 렙(반복) 카운트 — 무릎이 깊게 굽혀졌다가(내려감) 다시 펴지는(올라옴) 구간
          // 하나를 스쿼트 1회로 본다. 리포트 전용 집계라 세션 자동 종료 판단(judgmentHistoryRef)
          // 과는 별개로 처리한다.
          if (isDeepHold) {
            // (2026-09-08 추가) 새 렙이 시작되는 시점(서 있다가 방금 깊게 앉기 시작한 순간)에
            // movement 경고 노출 카운트를 리셋한다 — MOVEMENT_WARNING_MAX_PER_REP 캡이 렙마다
            // 새로 적용되게 하기 위함.
            if (!repInProgressRef.current) movementWarningCountRef.current = 0
            repInProgressRef.current = true
            if (!result.is_normal) {
              repHadIssueRef.current = true
              for (const issue of result.issues ?? []) {
                if (!repIssuesRef.current.some((seen) => seen.part === issue.part)) {
                  repIssuesRef.current.push({ part: issue.part })
                }
              }
            }
          } else if (repInProgressRef.current) {
            // 방금 "내려갔다가 다시 올라온" 구간이 끝났다 — 렙 1개 완료.
            repInProgressRef.current = false
            repHistoryRef.current = [
              ...repHistoryRef.current,
              { timestamp, is_normal: !repHadIssueRef.current, issues: repIssuesRef.current },
            ]
            repHadIssueRef.current = false
            repIssuesRef.current = []
            // (2026-09-08 추가) repHistory state를 렙이 끝날 때마다 갱신 — 원래는 세션
            // 종료(requestReport) 시점에만 한 번 반영됐는데, 그러면 진행 중인 세션 화면에
            // 실시간으로 "지금까지 몇 회"를 보여줄 방법이 없었다(SquatCoachingPage.jsx의
            // 숙련자 모드 목표 진행 표시가 이 값을 그대로 쓴다).
            setRepHistory(repHistoryRef.current)
          }

          let standingStepText = ''
          if (result.is_normal && !isDeepHold) {
            // 전신이 보이고 자세도 정상인데 아직 앉지 않은 상태 — 스쿼트 방법을 한 단계씩
            // 순서대로 안내한다. speak(안내) → pause(쉼) → 다음 단계 speak 순으로 반복.
            let justAdvanced = false
            if (standingPhaseRef.current === null) {
              standingStepIndexRef.current = 0
              standingPhaseRef.current = 'speak'
              standingPhaseStartRef.current = timestamp
              justAdvanced = true
            } else {
              const elapsed = timestamp - standingPhaseStartRef.current
              if (standingPhaseRef.current === 'speak' && elapsed >= STANDING_STEP_SPEAK_SEC) {
                standingPhaseRef.current = 'pause'
                standingPhaseStartRef.current = timestamp
              } else if (standingPhaseRef.current === 'pause') {
                const isLastStep = standingStepIndexRef.current === STANDING_STEPS.length - 1
                const pauseSec = isLastStep ? STANDING_STEP_LOOP_PAUSE_SEC : STANDING_STEP_PAUSE_SEC
                if (elapsed >= pauseSec) {
                  standingStepIndexRef.current = (standingStepIndexRef.current + 1) % STANDING_STEPS.length
                  standingPhaseRef.current = 'speak'
                  standingPhaseStartRef.current = timestamp
                  justAdvanced = true
                }
              }
            }
            standingStepText = STANDING_STEPS[standingStepIndexRef.current]
            // 단계 안내는 자체적으로 4초 말하기 + 4~7초 쉬기로 이미 속도가 정해져 있으므로
            // (justAdvanced일 때만) 그 타이밍을 그대로 쓰고, 위 일반 속도 제한(force 없는
            // 경로)은 적용하지 않는다 — 안 그러면 한 단계 안에서 두 번 말하게 될 수 있다.
            if (justAdvanced) {
              speak(standingStepText, timestamp, { force: true })
              logMessage(standingStepText, 'ok', timestamp)
            }
          } else {
            // 실제로 앉거나 이상 자세가 감지되면 서 있는 단계 안내를 초기화한다 — 다음에 다시
            // 서 있는 정상 상태가 되면 1단계부터 새로 시작한다.
            standingPhaseRef.current = null
            const text = coachingText(result, isDeepHold)
            speak(text, timestamp)
            logMessage(text, result.is_normal ? 'ok' : 'warn', timestamp)
          }

          setJudgeResult({ ...result, view: 'side', isDeepHold, standingStepText })

          if (judgmentHistoryRef.current.length % END_CHECK_EVERY_N_FRAMES === 0) {
            const end = await checkSessionEnd(judgmentHistoryRef.current, false)
            if (end?.should_end) transitionToFront(timestamp)
          }
        }
      } catch (err) {
        setJudgeError(`AI 서버 연결 실패: ${err.message}`)
      }
    } finally {
      tickRunningRef.current = false
    }
  }, [detectPose, speak, logMessage, checkSessionEnd, endSession, transitionToFront, sessionStage])
  // tick의 최신 참조를 들고 있어서, 아래 effect가 setInterval을 한 번만 걸어도
  // 매번 최신 tick(최신 detectPose/speak 등을 참조하는)을 부르게 한다.
  const tickRef = useRef(tick)
  tickRef.current = tick

  const start = useCallback(async () => {
    setCameraError('')
    setJudgeError('')
    setJudgeResult(null)
    setEndCheck(null)
    setSessionReport(null)
    setReportError('')
    if (recordedVideoUrlRef.current) URL.revokeObjectURL(recordedVideoUrlRef.current)
    recordedVideoUrlRef.current = null
    recordedVideoBlobRef.current = null
    setRecordedVideoUrl(null)
    recordedChunksRef.current = []
    framesRef.current = []
    setBufferCount(0)
    fullBodyMissingStreakRef.current = 0
    fullBodyVisibleStreakRef.current = 0
    judgmentHistoryRef.current = []
    lastSpokenRef.current = ''
    lastSpokenAtRef.current = -Infinity
    lastLoggedRef.current = ''
    setCoachingLog([])
    standingStepIndexRef.current = 0
    standingPhaseRef.current = null
    setSessionStage('side')
    frontJudgmentHistoryRef.current = []
    repHistoryRef.current = []
    metricsSumRef.current = {}
    frontMetricsSumRef.current = {}
    setRepHistory([]) // (2026-09-08 추가) 이전 세션의 repHistory state가 새 세션 시작 직후
    // 잠깐 그대로 남아있는 걸 막는다 — 이제 ActiveView가 이 값을 실시간으로 읽는다(위 참고).
    repInProgressRef.current = false
    repHadIssueRef.current = false
    repIssuesRef.current = []
    movementWarningCountRef.current = 0

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' }, audio: false })
      streamRef.current = stream
      // <video>는 phase가 'active'로 바뀐 뒤에야 화면에 그려지므로(ActiveView 참고), 여기서는
      // phase만 바꾸고 실제 srcObject 연결/재생/프레임 인터벌 시작은 아래 effect에서 한다 —
      // 안 그러면 아직 마운트 전인 videoRef.current가 null이라 srcObject 대입에서 에러가 난다.
      setPhase('active')
    } catch (err) {
      setCameraError(`카메라를 열지 못했어요: ${err.message} (브라우저의 카메라 권한을 확인해주세요)`)
    }
  }, [])

  // phase가 'active'가 되어 <video>가 실제로 마운트된 뒤 스트림을 연결한다(start() 참고).
  useEffect(() => {
    if (phase !== 'active') return
    const video = videoRef.current
    const stream = streamRef.current
    if (!video || !stream) return

    let cancelled = false
    video.srcObject = stream
    video.play().then(() => {
      if (cancelled) return
      startTimeRef.current = performance.now()
      intervalRef.current = setInterval(() => tickRef.current(), SAMPLE_INTERVAL_MS)

      // "방금 운동 다시보기" 녹화 시작 - 판정용 프레임 인터벌과 별개로 실제 화면 영상을 녹화.
      // 브라우저가 vp9를 지원 안 하면(구형 환경) 기본 webm으로 폴백하고, MediaRecorder 자체가
      // 없는 아주 오래된 환경이면 조용히 건너뛴다 - 다시보기/신고 영상첨부만 못 쓰게 될 뿐,
      // 코칭 자체는 그대로 진행된다.
      recordedChunksRef.current = []
      if (typeof MediaRecorder !== 'undefined') {
        try {
          const mimeType = MediaRecorder.isTypeSupported('video/webm;codecs=vp9')
            ? 'video/webm;codecs=vp9'
            : MediaRecorder.isTypeSupported('video/webm')
              ? 'video/webm'
              : ''
          const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream)
          recorder.ondataavailable = (e) => {
            if (e.data && e.data.size > 0) recordedChunksRef.current.push(e.data)
          }
          recorder.start()
          mediaRecorderRef.current = recorder
        } catch (err) {
          mediaRecorderRef.current = null
        }
      }
    })

    return () => {
      cancelled = true
    }
  }, [phase])

  const restart = useCallback(() => {
    setPhase('idle')
    setSessionReport(null)
    setReportError('')
    setJudgeResult(null)
    setEndCheck(null)
    if (recordedVideoUrlRef.current) URL.revokeObjectURL(recordedVideoUrlRef.current)
    recordedVideoUrlRef.current = null
    recordedVideoBlobRef.current = null
    setRecordedVideoUrl(null)
  }, [])

  // 페이지를 떠날 때 카메라가 계속 켜진 채로 남지 않도록 정리한다.
  useEffect(() => {
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
      if (streamRef.current) streamRef.current.getTracks().forEach((track) => track.stop())
      if (recordedVideoUrlRef.current) URL.revokeObjectURL(recordedVideoUrlRef.current)
    }
  }, [])

  return {
    videoRef,
    canvasRef,
    phase,
    cameraError,
    judgeResult,
    judgeError,
    fullBodyWarning,
    coachingLog,
    sessionStage,
    sessionHistory,
    repHistory,
    dailyStats,
    squatGoal,
    setSquatGoal,
    bufferCount,
    bufferMax: BUFFER_MAX,
    endCheck,
    sessionReport,
    reportLoading,
    reportError,
    ttsEnabled,
    setTtsEnabled,
    recordedVideoUrl,
    getRecordedVideoBlob: () => recordedVideoBlobRef.current,
    start,
    endSession: () => endSession('user_requested'),
    restart,
  }
}

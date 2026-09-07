/**
 * 실시간 스쿼트 코칭(측면 카메라)에 필요한 관절 각도/비율 계산 + 스켈레톤 오버레이 그리기.
 *
 * 계산 공식은 예전 ai/app/pose/angles.py를 JS로 그대로 이식한 것이고(현재는 "무거운 연산은
 * 클라이언트, 서버는 경량 수치만 비교" 원칙에 따라 프론트가 담당), pages/MlTestPage.jsx의
 * 검증된 구현(실제 사진/영상으로 확인된 임계값·보정 포함)을 그대로 따른다 — 두 곳에서 같은
 * 공식이 따로 어긋나지 않도록, 새로 만드는 페이지(SquatCoachingPage)는 이 모듈을 공유해서
 * 쓴다.
 *
 * 정면 카메라 전용 값(무릎 모임 knee_valgus_ratio 등)은 넣지 않았다 — 실시간 코칭 페이지는
 * 측면 카메라 한 대로만 진행하는 흐름이라(캘리브레이션/모드 선택/정면 세트는 이번 스코프에
 * 포함하지 않음, 2026-09-02 대화 기준) 지금은 필요 없다.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { usePoseLandmarker } from './usePoseLandmarker.js'
import { buildSideMetrics, drawSkeleton } from '../lib/squatPose.js'
import { AI_BASE } from '../lib/aiApi.js'


const SAMPLE_INTERVAL_MS = 200 // 실시간 판독 주기 — 대려 5fps
const BUFFER_MAX = 30 // 롤돁링 버퍼 최대 프레임 수(약 6초 분량)
const MIN_USABLE_FRAMES = 3 // 서버(judge_realtime_coaching)의 MIN_FRAMES와 동일한 기준
const JUDGE_WINDOW = 6 // 매 호출마뤌에서 서버에 보낼 "최근 N프레솄" 걬간 크기
const END_CHECK_EVERY_N_FRAMES = 10 // 종료 판정 은 프레임마다 부를 필요 없어 약 2초마다만 확인

async function postJson(path, body) {
  const res = await fetch(`${AI_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
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
  const [reportLoading, setReportLoading] = useState(false)
  const [reportError, setReportError] = useState('')
  const [ttsEnabled, setTtsEnabled] = useState(true)

  const videoRef = useRef(null)
  const canvasRef = useRef(null)
  const streamRef = useRef(null)
  const intervalRef = useRef(null)
  const offscreenRef = useRef(null)
  const startTimeRef = useRef(0)
  const tickRunningRef = useRef(false)
  const framesRef = useRef([]) // { timestamp, landmarks, metrics }
  const judgmentHistoryRef = useRef([]) // { timestamp, is_normal, issues[] }
  const lastSpokenRef = useRef('')

  const speak = useCallback(
    (text) => {
      if (!ttsEnabled || !text || text === lastSpokenRef.current) return
      if (!('speechSynthesis' in window)) return
      lastSpokenRef.current = text
      const utterance = new SpeechSynthesisUtterance(text)
      utterance.lang = 'ko-KR'
      window.speechSynthesis.cancel()
      window.speechSynthesis.speak(utterance)
    },
    [ttsEnabled],
  )

  const coachingText = (result) =>
    result.is_normal ? '좋아요, 지금 자세를 유지하세요' : (result.issues?.[0]?.message ?? '자세를 확인해주세요')

  const stop = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop())
      streamRef.current = null
    }
    if (videoRef.current) videoRef.current.srcObject = null
  }, [])

  const requestReport = useCallback(
    async (endReason) => {
      const history = judgmentHistoryRef.current
      if (history.length === 0) {
        setPhase('idle')
        return
      }
      setReportLoading(true)
      setReportError('')
      setSessionReport(null)
      try {
        const data = await postJson('/ai/session/report', {
          session_id: `squat-${Date.now()}`,
          frame_history: history.map(({ timestamp, is_normal, issues }) => ({
            timestamp,
            is_normal,
            issues: (issues ?? []).map((issue) => ({ part: issue.part })),
          })),
          session_duration_sec: history[history.length - 1].timestamp,
          previous_sessions: [], // TODO: 마이페이지 등에 세션 이력이 쌓이면 최근 N회를 넘겨 개선폭을 보여줄 수 있다.
          end_reason: endReason === 'user_requested' ? 'user_requested' : 'target_sustained',
        })
        setSessionReport(data)
        speak(data.summary_message)
      } catch (err) {
        setReportError(`AI 서버 연결 실패: ${err.message}`)
      } finally {
        setReportLoading(false)
      }
    },
    [speak],
  )

  const endSession = useCallback(
    (reason) => {
      stop()
      setPhase('report')
      requestReport(reason)
    },
    [stop, requestReport],
  )

  const checkSessionEnd = useCallback(async (userRequested) => {
    const history = judgmentHistoryRef.current
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
      const frame = { timestamp, landmarks, metrics: buildSideMetrics(landmarks) }
      const next = [...framesRef.current, frame].slice(-BUFFER_MAX)
      framesRef.current = next
      setBufferCount(next.length)
      drawSkeleton(video, canvasRef.current, landmarks)

      if (next.length < MIN_USABLE_FRAMES) return

      const start = Math.max(0, next.length - JUDGE_WINDOW)
      const angle_history = next.slice(start).map((f) => ({ timestamp: f.timestamp, ...f.metrics }))

      try {
        const result = await postJson('/ai/coaching/frame', { angle_history })
        setJudgeResult(result)
        setJudgeError('')

        judgmentHistoryRef.current = [
          ...judgmentHistoryRef.current,
          { timestamp, is_normal: result.is_normal, issues: result.issues ?? [] },
        ]
        speak(coachingText(result))

        if (judgmentHistoryRef.current.length % END_CHECK_EVERY_N_FRAMES === 0) {
          const end = await checkSessionEnd(false)
          if (end?.should_end) endSession(end.reason)
        }
      } catch (err) {
        setJudgeError(`AI 서버 연결 실패: ${err.message}`)
      }
    } finally {
      tickRunningRef.current = false
    }
  }, [detectPose, speak, checkSessionEnd, endSession])

  const start = useCallback(async () => {
    setCameraError('')
    setJudgeError('')
    setJudgeResult(null)
    setEndCheck(null)
    setSessionReport(null)
    setReportError('')
    framesRef.current = []
    setBufferCount(0)
    judgmentHistoryRef.current = []
    lastSpokenRef.current = ''

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' }, audio: false })
      streamRef.current = stream
      const video = videoRef.current
      video.srcObject = stream
      await video.play()
      startTimeRef.current = performance.now()
      intervalRef.current = setInterval(tick, SAMPLE_INTERVAL_MS)
      setPhase('active')
    } catch (err) {
      setCameraError(`카메라를 열지 못했어요: ${err.message} (브라우저의 카메라 권한을 확인해주세요)`)
    }
  }, [tick])

  const restart = useCallback(() => {
    setPhase('idle')
    setSessionReport(null)
    setReportError('')
    setJudgeResult(null)
    setEndCheck(null)
  }, [])

  // 페이지를 떠날 때 카메라가 계속 켜진 채로 남지 않도록 정리한다.
  useEffect(() => {
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
      if (streamRef.current) streamRef.current.getTracks().forEach((track) => track.stop())
    }
  }, [])

  return {
    videoRef,
    canvasRef,
    phase,
    cameraError,
    judgeResult,
    judgeError,
    bufferCount,
    bufferMax: BUFFER_MAX,
    endCheck,
    sessionReport,
    reportLoading,
    reportError,
    ttsEnabled,
    setTtsEnabled,
    start,
    endSession: () => endSession('user_requested'),
    restart,
  }
}

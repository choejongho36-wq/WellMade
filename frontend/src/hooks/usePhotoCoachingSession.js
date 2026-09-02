/**
 * 사진 코칭(②-A) 세션 훅 — 웹캠 촬영이 아니라 "사진 업로드" 흐름으로 바뀌었다(2026-09-02,
 * 시안 반영: 우측 상단 운동 선택 드롭다운 + 운동방법 모달, 좌측 "사진 미리보기" / 우측
 * "분석 결과" 2단 레이아웃). 업로드된 이미지를 오프스크린 캔버스에 그려 MlTestPage.jsx의
 * requestJudgment()와 동일한 방식으로 관절 좌표를 뽑고, AI-06(/ai/coaching/frame)에 물어봐
 * 정상/이상 판정과 교정 포인트를 받아온다.
 *
 * AI-06(judge_realtime_coaching)은 최소 3프레임(MIN_FRAMES)의 시계열이 있어야 판정하므로,
 * 사진 한 장에서 뽑은 값을 타임스탬프만 다르게 3번 복제해 보낸다 — 값이 동일하니 서버는
 * "정지" 상태로 인식해 실제 임계값 비교가 그대로 적용된다.
 *
 * 실시간 코칭(useSquatCoachingSession.js)과 마찬가지로 측면 카메라 한 장만 다루는 흐름이라
 * (정면 세트/무릎모임 값은 이번 스코프 밖), knee_valgus_ratio·torso_length_ratio(등 굽음,
 * 온보딩 캘리브레이션 필요)는 보내지 않는다 — 실제로 계산·판정 가능한 지표만 보낸다.
 */

import { useCallback, useRef, useState } from 'react'
import { usePoseLandmarker } from './usePoseLandmarker.js'
import { KEY_LANDMARKS, STANDING_KNEE_ANGLE_MIN, buildSideMetrics, renderPhotoWithSkeleton } from '../lib/squatPose.js'

const AI_BASE = import.meta.env.VITE_AI_BASE || 'http://localhost:8000'

const MAX_FILE_BYTES = 10 * 1024 * 1024 // 10MB — 업로드 버튼 아래 안내 문구와 동일한 기준
const ACCEPTED_TYPES = ['image/jpeg', 'image/png']

function loadImageFile(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file)
    const img = new Image()
    img.onload = () => resolve({ img, url })
    img.onerror = () => {
      URL.revokeObjectURL(url)
      reject(new Error('이미지를 읽지 못했어요.'))
    }
    img.src = url
  })
}

export function usePhotoCoachingSession() {
  const { detectPose } = usePoseLandmarker()

  const [phase, setPhase] = useState('idle') // idle | analyzing | result
  const [fileName, setFileName] = useState('')
  const [fileError, setFileError] = useState('')
  const [poseError, setPoseError] = useState('')
  const [judgeResult, setJudgeResult] = useState(null)
  const [judgeError, setJudgeError] = useState('')
  const [photoUrl, setPhotoUrl] = useState('')
  const [metrics, setMetrics] = useState(null) // buildSideMetrics() 결과 — 분석 결과 패널의 원본 수치
  const [avgVisibility, setAvgVisibility] = useState(null)

  const objectUrlRef = useRef('')
  const fileInputRef = useRef(null)

  const openFilePicker = useCallback(() => {
    fileInputRef.current?.click()
  }, [])

  const reset = useCallback(() => {
    if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current)
    objectUrlRef.current = ''
    setPhase('idle')
    setFileName('')
    setFileError('')
    setPoseError('')
    setJudgeResult(null)
    setJudgeError('')
    setPhotoUrl('')
    setMetrics(null)
    setAvgVisibility(null)
  }, [])

  const handleFile = useCallback(
    async (file) => {
      if (!file) return
      setFileError('')
      if (!ACCEPTED_TYPES.includes(file.type)) {
        setFileError('JPG 또는 PNG 파일만 업로드할 수 있어요.')
        return
      }
      if (file.size > MAX_FILE_BYTES) {
        setFileError('파일이 너무 커요. 10MB 이하 사진으로 올려주세요.')
        return
      }

      setPhase('analyzing')
      setFileName(file.name)
      setPoseError('')
      setJudgeResult(null)
      setJudgeError('')
      setMetrics(null)
      setAvgVisibility(null)

      let loaded
      try {
        loaded = await loadImageFile(file)
      } catch (err) {
        setFileError(err.message)
        setPhase('idle')
        return
      }
      if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current)
      objectUrlRef.current = loaded.url

      const offscreen = document.createElement('canvas')
      offscreen.width = loaded.img.naturalWidth
      offscreen.height = loaded.img.naturalHeight
      offscreen.getContext('2d').drawImage(loaded.img, 0, 0)

      try {
        const landmarks = await detectPose(offscreen)
        if (!landmarks) {
          setPoseError('사진에서 자세를 인식하지 못했어요. 전신이 잘 보이는 옆모습 사진으로 다시 올려주세요.')
          setPhotoUrl(offscreen.toDataURL('image/jpeg', 0.92))
          setPhase('result')
          return
        }

        const rendered = renderPhotoWithSkeleton(offscreen, landmarks)
        setPhotoUrl(rendered.toDataURL('image/jpeg', 0.92))
        setPhase('result')

        const keyVisibilities = Object.values(KEY_LANDMARKS).map((idx) => landmarks[idx]?.visibility ?? 1)
        setAvgVisibility(keyVisibilities.reduce((a, b) => a + b, 0) / keyVisibilities.length)

        const sideMetrics = buildSideMetrics(landmarks)
        setMetrics(sideMetrics)
        const angle_history = [0, 0.1, 0.2].map((timestamp) => ({ timestamp, ...sideMetrics }))
        const res = await fetch(`${AI_BASE}/ai/coaching/frame`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ angle_history }),
        })
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        setJudgeResult(await res.json())
      } catch (err) {
        setJudgeError(`AI 서버 연결 실패: ${err.message} (AI 서버가 localhost:8000에서 실행 중인지 확인해주세요)`)
      }
    },
    [detectPose],
  )

  const onFileInputChange = useCallback(
    (e) => {
      const file = e.target.files?.[0]
      e.target.value = '' // 같은 파일을 연달아 골라도 change 이벤트가 다시 뜨도록
      handleFile(file)
    },
    [handleFile],
  )

  const isDeepHold = metrics != null && metrics.knee_angle < STANDING_KNEE_ANGLE_MIN

  return {
    phase,
    fileName,
    fileError,
    poseError,
    judgeResult,
    judgeError,
    photoUrl,
    metrics,
    avgVisibility,
    isDeepHold,
    fileInputRef,
    openFilePicker,
    onFileInputChange,
    reset,
  }
}

/**
 * 사진 코칭(②-A) 세션 훅 — 2026-09-02 개편: 사진 1장(측면)만 받던 흐름을 정면(필수) +
 * 측면(선택) 2장으로 나눴다. 각 사진은 업로드 즉시 포즈를 인식해 드래그로 고칠 수 있는
 * "좌표 점"만 화면에 보여주고(usePhotoSlot), 실제 각도 재계산·AI 판정·LLM 분석 결과
 * 요약은 사용자가 "분석하기" 버튼을 눌렀을 때만(runAnalysis) 그 시점의 좌표로 수행한다 —
 * 점을 옮길 때마다 매번 다시 계산하지 않는다(2026-09-02 확인).
 *
 * 정면 사진: 무릎 모임(knee_valgus_ratio) 판정에 쓴다. 측면 사진이 함께 있으면 그 값을
 * AI-06(judge_realtime_coaching)의 AngleFrame에 실어 보내 서버가 판정하고(realtime.py가
 * 이미 이 필드를 지원함, 이번에 새로 짠 건 프론트에서 값을 계산해 보내는 부분뿐이다),
 * 측면 사진이 없으면 AI-06을 아예 호출하지 않고(knee_angle/hip_angle이 AngleFrame의
 * 필수 필드라 측면 없이는애초에 유효한 요청을 만들 수 없다) 프론트가 직접
 * KNEE_VALGUS_RATIO_THRESHOLD와 비교해 판정한다. 정면 사진이 실제로 정면처럼 보이지
 * 않으면(squatPose.js의 어깨 폭 검증) buildFrontMetrics가 null을 돌려주므로, 그 경우엔
 * 무릎모임 판정 자체가 나오지 않는다(2026-09-02, 측면 사진을 정면 칸에 올렸을 때 잘못된
 * 무릎모임 메시지가 뜨던 문제 수정).
 *
 * AI-06 호출 방식(3프레임 복제)은 기존과 동일 — hooks/usePhotoCoachingSession.js
 * 이전 버전, pages/MlTestPage.jsx의 requestJudgment() 참고.
 *
 * 판정 결과(is_normal/confidence/issues)가 나오면 곧바로 /ai/coaching/photo-summary를
 * 호출해 LLM(Nova)이 정리한 분석 결과 문장을 받아온다 — 판정 자체는 이 훅이 그대로
 * 갖고 있고, 문장만 서버가 만들어 돌려준다(app/coaching/photo_summary_llm.py).
 */

import { useCallback, useRef, useState } from 'react'
import { usePoseLandmarker } from './usePoseLandmarker.js'
import {
  buildFrontMetrics,
  buildSideMetrics,
  editablePointsToLandmarksArray,
  KEY_LANDMARKS,
  KNEE_VALGUS_MESSAGE,
  KNEE_VALGUS_RATIO_THRESHOLD,
  landmarksToEditablePoints,
} from '../lib/squatPose.js'

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

// 정면/측면 사진 슬롯 1개의 업로드→포즈 인식→(드래그로 수정 가능한) 좌표 상태를 관리한다.
// 두 슬롯(front/side)이 완전히 독립적으로 동작해야 해서(한쪽만 올려도 되므로) 같은 로직을
// usePhotoCoachingSession 안에서 두 번 호출한다.
function usePhotoSlot() {
  const { detectPose } = usePoseLandmarker()

  const [phase, setPhase] = useState('idle') // idle | analyzing | ready | error
  const [fileName, setFileName] = useState('')
  const [fileError, setFileError] = useState('')
  const [poseError, setPoseError] = useState('')
  const [photoUrl, setPhotoUrl] = useState('')
  const [points, setPoints] = useState(null)
  // 업로드한 사진의 가로/세로 비율(naturalWidth/naturalHeight) — 미리보기 박스를 3:4로
  // 고정하고 사진 전체를 잘리지 않게 보여줄 때(PHOTO_BOX_ASPECT_RATIO), 사진마다 다른
  // 여백 위치를 계산하는 데 쓴다(PhotoLandmarkEditor 참고). 사진마다 값이 다르므로
  // 업로드할 때 같이 저장해둔다.
  const [imageAspect, setImageAspect] = useState(null)
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
    setPhotoUrl('')
    setPoints(null)
    setImageAspect(null)
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
      setPoints(null)
      setImageAspect(null)
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
      setPhotoUrl(loaded.url)
      setImageAspect(loaded.img.naturalWidth / loaded.img.naturalHeight)

      const offscreen = document.createElement('canvas')
      offscreen.width = loaded.img.naturalWidth
      offscreen.height = loaded.img.naturalHeight
      offscreen.getContext('2d').drawImage(loaded.img, 0, 0)

      try {
        const landmarks = await detectPose(offscreen)
        if (!landmarks) {
          setPoseError('사진에서 자세를 인식하지 못했어요. 전신이 잘 보이는 사진으로 다시 올려주세요.')
          setPhase('error')
          return
        }

        setPoints(landmarksToEditablePoints(landmarks))
        setPhase('ready')

        const keyVisibilities = Object.values(KEY_LANDMARKS).map((idx) => landmarks[idx]?.visibility ?? 1)
        setAvgVisibility(keyVisibilities.reduce((a, b) => a + b, 0) / keyVisibilities.length)
      } catch (err) {
        setPoseError(`자세 인식에 실패했어요: ${err.message}`)
        setPhase('error')
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

  return {
    phase,
    fileName,
    fileError,
    poseError,
    photoUrl,
    points,
    setPoints,
    imageAspect,
    avgVisibility,
    fileInputRef,
    openFilePicker,
    onFileInputChange,
    reset,
  }
}

export function usePhotoCoachingSession() {
  const front = usePhotoSlot()
  const side = usePhotoSlot()

  const [analyzing, setAnalyzing] = useState(false)
  const [judgeResult, setJudgeResult] = useState(null) // { is_normal, confidence, issues }
  const [judgeError, setJudgeError] = useState('')
  const [summary, setSummary] = useState(null) // { summary_message, generation_source }
  const [summaryError, setSummaryError] = useState('')

  const canAnalyze = front.phase === 'ready' && !analyzing

  const runAnalysis = useCallback(async () => {
    if (front.phase !== 'ready' || !front.points) return

    setAnalyzing(true)
    setJudgeError('')
    setSummaryError('')
    setJudgeResult(null)
    setSummary(null)

    const hasSide = side.phase === 'ready' && !!side.points

    try {
      const frontMetrics = buildFrontMetrics(editablePointsToLandmarksArray(front.points))

      let is_normal
      let confidence
      let issues
      let metrics

      if (hasSide) {
        const sideMetrics = buildSideMetrics(editablePointsToLandmarksArray(side.points))
        metrics = { ...sideMetrics, ...frontMetrics }
        const angle_history = [0, 0.1, 0.2].map((timestamp) => ({ timestamp, ...metrics }))
        const res = await fetch(`${AI_BASE}/ai/coaching/frame`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ angle_history }),
        })
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const judged = await res.json()
        is_normal = judged.is_normal
        confidence = judged.confidence
        issues = judged.issues
      } else {
        // 측면 사진이 없으면 knee_angle/hip_angle(AI-06 필수 필드)을 만들 수 없어
        // AI-06을 호출하지 않는다 — 정면에서 계산 가능한 무릎 모임만 프론트가 직접 판정한다.
        // frontMetrics.knee_valgus_ratio가 null이면(정면 사진처럼 보이지 않을 때 포함)
        // 무릎모임 이상 없음으로 처리한다 — 판정을 아예 하지 않은 것이지 "정상"이라고
        // 단정하는 게 아니므로 신뢰도(confidence)를 낮게 잡는다.
        metrics = { ...frontMetrics }
        const ratio = frontMetrics.knee_valgus_ratio
        const hasValgus = ratio != null && ratio < KNEE_VALGUS_RATIO_THRESHOLD
        is_normal = !hasValgus
        confidence = ratio != null ? 0.6 : 0.3
        issues = hasValgus ? [{ part: 'knee_valgus', message: KNEE_VALGUS_MESSAGE }] : []
      }

      setJudgeResult({ is_normal, confidence, issues })

      try {
        const summaryRes = await fetch(`${AI_BASE}/ai/coaching/photo-summary`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            is_normal,
            confidence,
            issues,
            metrics,
            has_side_photo: hasSide,
          }),
        })
        if (!summaryRes.ok) throw new Error(`HTTP ${summaryRes.status}`)
        setSummary(await summaryRes.json())
      } catch (err) {
        setSummaryError(`분석 결과 요약을 불러오지 못했어요: ${err.message}`)
      }
    } catch (err) {
      setJudgeError(`AI 서버 연결 실패: ${err.message} (AI 서버가 localhost:8000에서 실행 중인지 확인해주세요)`)
    } finally {
      setAnalyzing(false)
    }
  }, [front.phase, front.points, side.phase, side.points])

  return {
    front,
    side,
    analyzing,
    canAnalyze,
    judgeResult,
    judgeError,
    summary,
    summaryError,
    runAnalysis,
  }
}

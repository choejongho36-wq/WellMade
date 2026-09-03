/**
 * 사진 코칭(②-A) 세션 훅 — 2026-09-02 개편: 사진 1장(측면)만 받던 흐름을 정면(선택) +
 * 측면(필수) 2장으로 나눴다. 각 사진은 업로드 즉시 포즈를 인식해 드래그로 고칠 수 있는
 * "좌표 점"만 화면에 보여주고(usePhotoSlot), 실제 각도 재계산·AI 판정·LLM 분석 결과
 * 요약은 사용자가 "분석하기" 버튼을 눌렀을 때만(runAnalysis) 그 시점의 좌표로 수행한다 —
 * 점을 옮길 때마다 매번 다시 계산하지 않는다(2026-09-02 확인).
 *
 * 측면 사진이 필수인 이유: AI-06(judge_realtime_coaching)의 실제 판정(무릎/엉덩이 각도,
 * 발뒤꿈치, 무릎-발끝, 무게중심 등)이 전부 측면 사진에서 뽑는 knee_angle/hip_angle 등을
 * 필요로 한다 — 이 값들은 AngleFrame의 필수 필드라 측면 없이는 AI-06을 호출할 수조차
 * 없다(2026-09-02 정정: 처음엔 정면을 필수로 뒀었는데, 실제 판정의 핵심이 측면 값이라
 * 측면을 필수로 바꿨다). 정면 사진은 있으면 무릎 모임(knee_valgus_ratio)만 추가로
 * 계산해서 측면 값과 합쳐 같이 보낸다 — 없어도 측면만으로 나머지 판정은 그대로 된다.
 * 정면 사진이 실제로 정면처럼 보이지 않으면(squatPose.js의 어깨 폭 검증)
 * buildFrontMetrics가 null을 돌려주므로, 그 경우엔 무릎모임 판정 자체가 나오지 않는다
 * (측면 사진을 정면 칸에 올렸을 때 잘못된 무릎모임 메시지가 뜨던 문제 수정, 이전 버전).
 *
 * AI-06 호출 방식(3프레임 복제)은 기존과 동일 — hooks/usePhotoCoachingSession.js
 * 이전 버전, pages/MlTestPage.jsx의 requestJudgment() 참고.
 *
 * 판정 결과(is_normal/confidence/issues)가 나오면 곧바로 /ai/coaching/photo-summary를
 * 호출해 LLM(Nova)이 정리한 분석 결과 문장을 받아온다 — 판정 자체는 이 훅이 그대로
 * 갖고 있고, 문장만 서버가 만들어 돌려준다(app/coaching/photo_summary_llm.py). 정면이
 * 선택으로 바뀌면서 이 API에 보내는 플래그도 has_side_photo(측면 포함 여부)에서
 * has_front_photo(정면 포함 여부)로 바뀌었다 — 이제 측면은 항상 있어서 "포함 여부"를
 * 알려줄 의미가 없고, 대신 정면 포함 여부가 문장에 영향을 준다.
 *
 * (2026-09-03 추가) 사진에 여러 명이 찍혀 있으면 usePoseLandmarker({ numPoses: 5 })로
 * 최대 5명까지 인식하고, 2명 이상이면 자동으로 아무나 고르지 않는다 — phase를 'choosing'
 * 으로 두고 candidates(후보 랜드마크 배열들)를 노출해서, 페이지 쪽(PersonPickerOverlay)이
 * 사진 위에 사람별 테두리를 그려 사용자가 직접 고르게 한다. choosePerson(index)을 부르면
 * 그 시점에 비로소 points/avgVisibility가 채워지고 phase가 'ready'로 넘어간다 — 1명만
 * 인식됐을 때는 이 단계 없이 바로 'ready'로 넘어가던 기존 동작 그대로 유지.
 *
 * (2026-09-03 추가) 사진을 고르면 포즈 인식을 곧바로 돌리지 않고 phase를 'cropping'으로
 * 두어 먼저 자르기 화면(PhotoCropOverlay)을 보여준다 — cropRect(원본 사진 기준 정규화
 * 좌표)를 노출해서 페이지 쪽이 드래그로 조절하게 하고, "자르기 적용"을 누르면 applyCrop()
 * 이 그 영역만 canvas로 그려낸 사진으로 교체한 뒤 포즈 인식을 시작한다. "건너뛰기"를
 * 누르면 skipCrop()이 원본 그대로 포즈 인식을 시작한다 — 둘 다 내부적으로 같은
 * runDetection()을 공유해서, 그 이후(1명/여러 명 분기)는 기존 동작과 동일하다.
 */

import { useCallback, useRef, useState } from 'react'
import { usePoseLandmarker } from './usePoseLandmarker.js'
import { buildFrontMetrics, buildSideMetrics, editablePointsToLandmarksArray, KEY_LANDMARKS, landmarksToEditablePoints } from '../lib/squatPose.js'

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
  const { detectAllPoses } = usePoseLandmarker({ numPoses: 5 })

  const [phase, setPhase] = useState('idle') // idle | analyzing | choosing | ready | error
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
  // (2026-09-03 추가) 여러 명이 인식됐을 때 사용자가 고르기 전까지 대기하는 후보 랜드마크
  // 배열들 — phase가 'choosing'일 때만 값이 있다.
  const [candidates, setCandidates] = useState(null)
  // (2026-09-03 추가) 자르기 영역 — 원본 사진 기준 정규화 좌표({x, y, width, height},
  // 0~1). phase가 'cropping'일 때만 값이 있다. 실제 자르기(applyCrop)에서 이 값과
  // loadedImageRef의 원본 이미지를 같이 써서 픽셀 좌표로 변환한다.
  const [cropRect, setCropRect] = useState(null)

  const objectUrlRef = useRef('')
  const fileInputRef = useRef(null)
  // (2026-09-03 추가) 업로드 직후 로드한 원본 <img> 엘리먼트 — 자르기(applyCrop) 또는
  // 건너뛰기(skipCrop)를 고를 때까지 들고 있다가, 그 시점에 canvas로 그려 포즈 인식에
  // 넘긴다. photoUrl(화면 표시용 objectURL)과 별개로 원본 픽셀 데이터에 접근하기 위함.
  const loadedImageRef = useRef(null)

  const openFilePicker = useCallback(() => {
    fileInputRef.current?.click()
  }, [])

  const reset = useCallback(() => {
    if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current)
    objectUrlRef.current = ''
    loadedImageRef.current = null
    setPhase('idle')
    setFileName('')
    setFileError('')
    setPoseError('')
    setPhotoUrl('')
    setPoints(null)
    setImageAspect(null)
    setAvgVisibility(null)
    setCandidates(null)
    setCropRect(null)
  }, [])

  // 인식된 랜드마크 1명분을 points/avgVisibility 상태로 반영하고 phase를 'ready'로 바꾼다 —
  // 1명만 인식돼 자동으로 넘어갈 때와, 여러 명 중 하나를 골랐을 때(choosePerson) 둘 다
  // 이 함수를 공유한다.
  const applyLandmarks = useCallback((landmarks) => {
    setPoints(landmarksToEditablePoints(landmarks))
    setPhase('ready')
    setCandidates(null)

    const keyVisibilities = Object.values(KEY_LANDMARKS).map((idx) => landmarks[idx]?.visibility ?? 1)
    setAvgVisibility(keyVisibilities.reduce((a, b) => a + b, 0) / keyVisibilities.length)
  }, [])

  // PersonPickerOverlay에서 사용자가 특정 사람을 탭했을 때 호출 — candidates[index]를
  // 최종 선택으로 확정한다.
  const choosePerson = useCallback(
    (index) => {
      const landmarks = candidates?.[index]
      if (!landmarks) return
      applyLandmarks(landmarks)
    },
    [candidates, applyLandmarks],
  )

  // 실제 포즈 인식 단계 — 자르기를 적용했든(applyCrop) 건너뛰었든(skipCrop) canvas 하나를
  // 받아 그 위에서 인식을 돌린다. 1명이면 바로 확정, 여러 명이면 'choosing'으로 대기,
  // 없으면 에러 — 기존과 동일한 분기.
  const runDetection = useCallback(
    async (canvas) => {
      setPhase('analyzing')
      try {
        const allLandmarks = await detectAllPoses(canvas)
        if (!allLandmarks || allLandmarks.length === 0) {
          setPoseError('사진에서 자세를 인식하지 못했어요. 전신이 잘 보이는 사진으로 다시 올려주세요.')
          setPhase('error')
          return
        }

        // (2026-09-03) 여러 명이 인식되면 자동으로 아무나 고르지 않고, 사용자가 직접 고를
        // 때까지 'choosing' 상태로 대기한다 — PersonPickerOverlay 참고.
        if (allLandmarks.length > 1) {
          setCandidates(allLandmarks)
          setPhase('choosing')
          return
        }

        applyLandmarks(allLandmarks[0])
      } catch (err) {
        setPoseError(`자세 인식에 실패했어요: ${err.message}`)
        setPhase('error')
      }
    },
    [detectAllPoses, applyLandmarks],
  )

  // "건너뛰기" — 자르지 않고 원본 이미지 그대로 인식을 돌린다(기존 동작과 동일).
  const skipCrop = useCallback(() => {
    const img = loadedImageRef.current
    if (!img) return
    const canvas = document.createElement('canvas')
    canvas.width = img.naturalWidth
    canvas.height = img.naturalHeight
    canvas.getContext('2d').drawImage(img, 0, 0)
    runDetection(canvas)
  }, [runDetection])

  // "자르기 적용" — cropRect(정규화 좌표)를 원본 이미지 픽셀 좌표로 바꿔 그 영역만 새
  // canvas에 그린다. 화면 표시용 photoUrl도 이 canvas에서 만든 이미지로 교체해야
  // points(정규화 좌표)와 실제 보이는 사진이 어긋나지 않는다 — 인식은 이 canvas와
  // photoUrl 교체를 동시에(비동기 순서 상관없이) 진행한다.
  const applyCrop = useCallback(() => {
    const img = loadedImageRef.current
    if (!img || !cropRect) return
    const sx = cropRect.x * img.naturalWidth
    const sy = cropRect.y * img.naturalHeight
    const sw = Math.max(1, cropRect.width * img.naturalWidth)
    const sh = Math.max(1, cropRect.height * img.naturalHeight)

    const canvas = document.createElement('canvas')
    canvas.width = sw
    canvas.height = sh
    canvas.getContext('2d').drawImage(img, sx, sy, sw, sh, 0, 0, sw, sh)

    canvas.toBlob((blob) => {
      if (!blob) return
      const url = URL.createObjectURL(blob)
      if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current)
      objectUrlRef.current = url
      setPhotoUrl(url)
    }, 'image/png')

    setImageAspect(sw / sh)
    runDetection(canvas)
  }, [cropRect, runDetection])

  const handleFile = useCallback(async (file) => {
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

    setPhase('analyzing') // 사진 로드 자체는 순간적이라, 별도 phase 없이 기존 로딩 표시를 재사용
    setFileName(file.name)
    setPoseError('')
    setPoints(null)
    setImageAspect(null)
    setAvgVisibility(null)
    setCandidates(null)
    setCropRect(null)

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
    loadedImageRef.current = loaded.img

    // (2026-09-03) 포즈 인식을 바로 돌리지 않고, 먼저 자르기 화면을 보여준다 — 사용자가
    // "자르기 적용"(applyCrop)/"건너뛰기"(skipCrop)를 고르면 그때 인식이 시작된다.
    setCropRect({ x: 0, y: 0, width: 1, height: 1 })
    setPhase('cropping')
  }, [])

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
    candidates,
    choosePerson,
    cropRect,
    setCropRect,
    applyCrop,
    skipCrop,
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

  const canAnalyze = side.phase === 'ready' && !analyzing

  const runAnalysis = useCallback(async () => {
    if (side.phase !== 'ready' || !side.points) return

    setAnalyzing(true)
    setJudgeError('')
    setSummaryError('')
    setJudgeResult(null)
    setSummary(null)

    const hasFront = front.phase === 'ready' && !!front.points

    try {
      const sideMetrics = buildSideMetrics(editablePointsToLandmarksArray(side.points))
      // 정면 사진이 있으면 무릎모임(knee_valgus_ratio)을 추가로 계산해 측면 값과 합친다 —
      // 없으면 측면 값만으로 AI-06을 부른다(knee_valgus_ratio가 없으면 서버가 그 항목만
      // 건너뛴다).
      const frontMetrics = hasFront ? buildFrontMetrics(editablePointsToLandmarksArray(front.points)) : {}
      const metrics = { ...sideMetrics, ...frontMetrics }

      const angle_history = [0, 0.1, 0.2].map((timestamp) => ({ timestamp, ...metrics }))
      const res = await fetch(`${AI_BASE}/ai/coaching/frame`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ angle_history }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const judged = await res.json()
      const { is_normal, confidence, issues } = judged

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
            has_front_photo: hasFront,
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

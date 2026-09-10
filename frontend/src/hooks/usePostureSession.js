/**
 * 정지 자세 분석 세션 훅.
 *
 * 사진 1장(정면 또는 측면)을 받아 → 브라우저에서 좌표 추출 → 사용자가
 * "분석하기"를 눌렀을 때 posture-ai 서버에 좌표만 전송 → 판정 결과와
 * 코멘트를 돌려준다.
 *
 * 사진 업로드와 분석을 분리한 이유(팀 usePhotoCoachingSession과 같은 흐름):
 *   올리자마자 분석하면 사진을 잘못 골랐을 때도 API 호출이 나가 비용이
 *   발생하고, 사용자가 사진을 확인·교체할 여지가 없다. 업로드 시점에는
 *   좌표 추출(브라우저 내 계산, 무료)까지만 하고, 서버 호출은 버튼을
 *   눌렀을 때만 한다.
 *
 * 팀 usePhotoCoachingSession(운동 자세)과는 별개다. 그쪽은 스쿼트 판정에
 * 필요한 각도를 프론트에서 계산해 보내지만, 여기는 계산을 전혀 하지 않고
 * 좌표만 넘긴다 — 정지 자세의 각도·판정은 전부 서버(posture-ai)의 검증
 * 파이프라인이 담당한다("판단은 LLM, 계산은 코드" 원칙).
 *
 * usePoseLandmarker는 팀 훅을 그대로 재사용한다. 스쿼트 의존성이 없는 순수
 * MediaPipe 로딩 훅이고, 모델 URL이 두 곳에 흩어지는 것을 막기 위함이다.
 */

import { useCallback, useRef, useState } from 'react'
import { usePoseLandmarker } from './usePoseLandmarker.js'
import { analyzePosture } from '../lib/postureApi.js'

const MAX_FILE_BYTES = 10 * 1024 * 1024 // 10MB — 팀 사진 코칭과 같은 기준
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

/**
 * @param {'front'|'side'} view
 */
export function usePostureSession(view) {
  const { detectPose } = usePoseLandmarker()
  const fileInputRef = useRef(null)

  // phase: idle(사진 없음) | detecting(좌표 추출 중) | ready(분석 가능) | error
  const [phase, setPhase] = useState('idle')
  const [photoUrl, setPhotoUrl] = useState(null)
  const [fileName, setFileName] = useState('')
  const [fileError, setFileError] = useState(null)

  // 추출된 좌표와 원본 크기 — 분석 버튼을 눌렀을 때 서버로 보낸다.
  const payloadRef = useRef(null)
  const [avgVisibility, setAvgVisibility] = useState(null)

  const [analyzing, setAnalyzing] = useState(false)
  const [result, setResult] = useState(null)
  const [analyzeError, setAnalyzeError] = useState(null)

  const openFilePicker = useCallback(() => {
    fileInputRef.current?.click()
  }, [])

  const reset = useCallback(() => {
    setPhotoUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev)
      return null
    })
    setPhase('idle')
    setFileName('')
    setFileError(null)
    setAvgVisibility(null)
    setResult(null)
    setAnalyzeError(null)
    payloadRef.current = null
  }, [])

  /** 파일 선택 → 좌표 추출까지만. 서버 호출은 하지 않는다. */
  const handleFile = useCallback(
    async (file) => {
      setFileError(null)
      setAnalyzeError(null)
      setResult(null)

      if (!ACCEPTED_TYPES.includes(file.type)) {
        setFileError('JPG 또는 PNG 파일만 올릴 수 있어요.')
        setPhase('error')
        return
      }
      if (file.size > MAX_FILE_BYTES) {
        setFileError('사진 용량은 10MB까지 가능해요.')
        setPhase('error')
        return
      }

      let loaded
      try {
        loaded = await loadImageFile(file)
      } catch (err) {
        setFileError(err.message)
        setPhase('error')
        return
      }

      setPhotoUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev)
        return loaded.url
      })
      setFileName(file.name)
      setPhase('detecting')

      // 브라우저에서 좌표 추출 — 사진은 여기서 끝, 서버로 가지 않는다.
      const landmarks = await detectPose(loaded.img)
      if (!landmarks || landmarks.length === 0) {
        setFileError('사진에서 사람을 인식하지 못했어요. 전신이 보이도록 다시 촬영해 주세요.')
        setPhase('error')
        return
      }

      payloadRef.current = {
        landmarks,
        imageWidth: loaded.img.naturalWidth,
        imageHeight: loaded.img.naturalHeight,
      }
      const visibilities = landmarks
        .map((p) => (typeof p.visibility === 'number' ? p.visibility : null))
        .filter((v) => v != null)
      setAvgVisibility(
        visibilities.length
          ? visibilities.reduce((a, b) => a + b, 0) / visibilities.length
          : null,
      )
      setPhase('ready')
    },
    [detectPose],
  )

  const onFileInputChange = useCallback(
    (event) => {
      const file = event.target.files?.[0]
      if (file) handleFile(file)
      event.target.value = '' // 같은 파일을 다시 골라도 onChange가 뜨도록
    },
    [handleFile],
  )

  /** 사용자가 "분석하기"를 눌렀을 때만 서버를 호출한다. */
  const runAnalysis = useCallback(async () => {
    if (!payloadRef.current || analyzing) return

    setAnalyzing(true)
    setAnalyzeError(null)
    try {
      const { landmarks, imageWidth, imageHeight } = payloadRef.current
      const data = await analyzePosture(view, landmarks, imageWidth, imageHeight)
      setResult(data)
    } catch (err) {
      setAnalyzeError(err.message)
    } finally {
      setAnalyzing(false)
    }
  }, [analyzing, view])

  return {
    // 사진 슬롯
    phase,
    photoUrl,
    fileName,
    fileError,
    avgVisibility,
    fileInputRef,
    openFilePicker,
    onFileInputChange,
    reset,

    // 분석
    canAnalyze: phase === 'ready' && !analyzing,
    analyzing,
    result,
    analyzeError,
    runAnalysis,
  }
}

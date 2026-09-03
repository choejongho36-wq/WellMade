import { useCallback, useRef, useState } from 'react'
import { FilesetResolver, PoseLandmarker } from '@mediapipe/tasks-vision'

const WASM_BASE = 'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision/wasm'
const MODEL_URL =
  'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task'

// 자세 측정(기울기/정렬)에 실제로 쓰는 관절만 추림 — 얼굴 세부/손가락 등은 제외
export const POSTURE_LANDMARKS = {
  leftEar: 7,
  rightEar: 8,
  leftShoulder: 11,
  rightShoulder: 12,
  leftHip: 23,
  rightHip: 24,
  leftKnee: 25,
  rightKnee: 26,
  leftAnkle: 27,
  rightAnkle: 28,
}

// (2026-09-03 추가) numPoses — 한 사진에서 최대 몇 명까지 인식할지. 기본값 1은 기존
// 동작(실시간 웹캠 코칭 등)과 완전히 동일하게 유지하고, 사진 코칭 업로드처럼 "여러 명이
// 있으면 고르게 해달라"는 곳에서만 usePoseLandmarker({ numPoses: 5 })로 늘려 쓴다 —
// 실시간 코칭은 프레임마다 매번 여러 명을 계산하면 성능 부담이 커서 그대로 1명 유지.
export function usePoseLandmarker({ numPoses = 1 } = {}) {
  const landmarkerRef = useRef(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const getLandmarker = useCallback(async () => {
    if (!landmarkerRef.current) {
      const vision = await FilesetResolver.forVisionTasks(WASM_BASE)
      landmarkerRef.current = await PoseLandmarker.createFromOptions(vision, {
        baseOptions: { modelAssetPath: MODEL_URL },
        runningMode: 'IMAGE',
        numPoses,
      })
    }
    return landmarkerRef.current
  }, [numPoses])

  // 가장 신뢰도 높은 사람 1명만 필요할 때 쓰는 기존 동작(실시간 코칭, 각도 계산 등) —
  // numPoses를 늘려 만들었어도 이 함수는 항상 landmarks[0](가장 신뢰도 높은 사람)만 쓴다.
  const detectPose = useCallback(
    async (imageElement) => {
      setLoading(true)
      setError(null)
      try {
        const landmarker = await getLandmarker()
        const { landmarks } = landmarker.detect(imageElement)
        const raw = landmarks[0]
        if (!raw) return null

        // AI 서버 스키마(app/schemas.py Landmark)가 33개 전체를 인덱스 순서 그대로 요구함
        return raw.map(({ x, y, z, visibility }) => ({ x, y, z, visibility }))
      } catch (err) {
        setError(err)
        return null
      } finally {
        setLoading(false)
      }
    },
    [getLandmarker],
  )

  // (2026-09-03 추가) 인식된 사람 전원의 33개 랜드마크 배열을 그대로 돌려준다 — 사진에
  // 여러 명이 있을 때 자동으로 1명만 고르지 않고 사용자가 직접 고를 수 있게 하려면
  // (usePhotoCoachingSession.js 참고) 호출부가 전체 후보를 받아서 직접 다뤄야 한다.
  const detectAllPoses = useCallback(
    async (imageElement) => {
      setLoading(true)
      setError(null)
      try {
        const landmarker = await getLandmarker()
        const { landmarks } = landmarker.detect(imageElement)
        if (!landmarks || landmarks.length === 0) return null
        return landmarks.map((raw) => raw.map(({ x, y, z, visibility }) => ({ x, y, z, visibility })))
      } catch (err) {
        setError(err)
        return null
      } finally {
        setLoading(false)
      }
    },
    [getLandmarker],
  )

  return { detectPose, detectAllPoses, loading, error }
}

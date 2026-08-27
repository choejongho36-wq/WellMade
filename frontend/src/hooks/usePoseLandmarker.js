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

export function usePoseLandmarker() {
  const landmarkerRef = useRef(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const getLandmarker = useCallback(async () => {
    if (!landmarkerRef.current) {
      const vision = await FilesetResolver.forVisionTasks(WASM_BASE)
      landmarkerRef.current = await PoseLandmarker.createFromOptions(vision, {
        baseOptions: { modelAssetPath: MODEL_URL },
        runningMode: 'IMAGE',
      })
    }
    return landmarkerRef.current
  }, [])

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

  return { detectPose, loading, error }
}

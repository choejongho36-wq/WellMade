/**
 * 정지 자세 분석 세션 훅.
 *
 * 사진 1장(정면 또는 측면)을 받아 → 브라우저에서 좌표 추출 → posture-ai
 * 서버에 좌표만 전송 → 판정 결과와 코멘트를 돌려준다.
 *
 * 팀의 usePhotoCoachingSession(운동 자세)과는 별개다. 그쪽은 스쿼트 판정에
 * 필요한 무릎/엉덩이 각도를 프론트에서 계산해 보내지만, 여기는 계산을 전혀
 * 하지 않고 좌표만 넘긴다 — 정지 자세의 각도·판정은 전부 서버(posture-ai)의
 * 검증 파이프라인이 담당하기 때문이다("판단은 LLM, 계산은 코드" 원칙).
 *
 * usePoseLandmarker는 팀 훅을 그대로 재사용한다. 스쿼트 의존성이 없는 순수
 * MediaPipe 로딩 훅이고, 모델 URL이 두 곳에 흩어지는 것을 막기 위함이다.
 */

import { useCallback, useState } from 'react'
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

  const [previewUrl, setPreviewUrl] = useState(null)
  const [status, setStatus] = useState('idle') // idle | detecting | analyzing | done | error
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  const reset = useCallback(() => {
    setPreviewUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev)
      return null
    })
    setStatus('idle')
    setResult(null)
    setError(null)
  }, [])

  const analyze = useCallback(
    async (file) => {
      setError(null)
      setResult(null)

      if (!ACCEPTED_TYPES.includes(file.type)) {
        setError('JPG 또는 PNG 파일만 올릴 수 있어요.')
        setStatus('error')
        return
      }
      if (file.size > MAX_FILE_BYTES) {
        setError('사진 용량은 10MB까지 가능해요.')
        setStatus('error')
        return
      }

      let loaded
      try {
        loaded = await loadImageFile(file)
      } catch (err) {
        setError(err.message)
        setStatus('error')
        return
      }

      setPreviewUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev)
        return loaded.url
      })

      // 1) 브라우저에서 좌표 추출 — 사진은 여기서 끝, 서버로 가지 않는다.
      setStatus('detecting')
      const landmarks = await detectPose(loaded.img)
      if (!landmarks) {
        setError('사진에서 사람을 인식하지 못했어요. 전신이 보이도록 다시 촬영해 주세요.')
        setStatus('error')
        return
      }

      // 2) 좌표만 서버로 전송
      setStatus('analyzing')
      try {
        const data = await analyzePosture(
          view,
          landmarks,
          loaded.img.naturalWidth,
          loaded.img.naturalHeight,
        )
        setResult(data)
        setStatus('done')
      } catch (err) {
        setError(err.message)
        setStatus('error')
      }
    },
    [detectPose, view],
  )

  return {
    previewUrl,
    status,
    result,
    error,
    analyze,
    reset,
    isBusy: status === 'detecting' || status === 'analyzing',
  }
}

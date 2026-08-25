import { useRef, useState } from 'react'
import './PosturePage.css'
import PageShell from '../components/PageShell.jsx'
import { usePoseLandmarker } from '../hooks/usePoseLandmarker.js'

const PREVIEW_WIDTH = 480
const PREVIEW_HEIGHT = 680

// object-fit: contain으로 표시되는 실제 사진 영역(레터박스 offset 포함)에 맞춰 점을 찍음
function drawLandmarks(canvas, image, landmarks) {
  const boxW = image.clientWidth
  const boxH = image.clientHeight
  const scale = Math.min(boxW / image.naturalWidth, boxH / image.naturalHeight)
  const renderedW = image.naturalWidth * scale
  const renderedH = image.naturalHeight * scale
  const offsetX = (boxW - renderedW) / 2
  const offsetY = (boxH - renderedH) / 2

  canvas.width = boxW
  canvas.height = boxH
  const ctx = canvas.getContext('2d')
  ctx.clearRect(0, 0, boxW, boxH)
  ctx.fillStyle = '#da291c'
  landmarks.forEach(({ x, y }) => {
    ctx.beginPath()
    ctx.arc(offsetX + x * renderedW, offsetY + y * renderedH, 4, 0, Math.PI * 2)
    ctx.fill()
  })
}

const AI_BASE = 'http://localhost:8000'

function PoseCaptureCard({ label, onDetected }) {
  const [imageUrl, setImageUrl] = useState(null)
  const [status, setStatus] = useState('')
  const imgRef = useRef(null)
  const canvasRef = useRef(null)
  const { detectPose, loading } = usePoseLandmarker()

  const handleFile = (e) => {
    const file = e.target.files[0]
    if (!file) return
    setImageUrl(URL.createObjectURL(file))
    setStatus('')
  }

  const handleImageLoad = async () => {
    const landmarks = await detectPose(imgRef.current)
    if (!landmarks) {
      setStatus('관절을 인식하지 못했어요. 다른 사진으로 시도해주세요.')
      return
    }
    drawLandmarks(canvasRef.current, imgRef.current, landmarks)
    setStatus(`관절 ${landmarks.length}개 인식 완료`)
    onDetected(landmarks)
  }

  return (
    <div className="pose-card">
      <div className="pose-card-body">
        <div className="pose-card-title">{label}</div>
        <input type="file" accept="image/*" onChange={handleFile} />
        {imageUrl && (
          <div
            style={{
              position: 'relative',
              marginTop: 12,
              width: PREVIEW_WIDTH,
              height: PREVIEW_HEIGHT,
              background: '#f0efe9',
              borderRadius: 8,
              overflow: 'hidden',
            }}
          >
            <img
              ref={imgRef}
              src={imageUrl}
              alt={label}
              onLoad={handleImageLoad}
              style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block' }}
            />
            <canvas
              ref={canvasRef}
              style={{ position: 'absolute', top: 0, left: 0, pointerEvents: 'none' }}
            />
          </div>
        )}
        <p className="pcard-desc">{loading ? '분석 중...' : status}</p>
      </div>
    </div>
  )
}

function PosturePage() {
  const [insight, setInsight] = useState(null)
  const [insightError, setInsightError] = useState('')

  // ponytail: 성별/출생년도 입력 UI는 아직 없음 — 연결 테스트 목적으로 임시 고정값 사용
  const handleFrontDetected = async (landmarks) => {
    setInsightError('')
    try {
      const res = await fetch(`${AI_BASE}/ai/onboarding/posture-insight`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ front_landmarks: landmarks, gender: 'M', birth_year: 2000 }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setInsight(await res.json())
    } catch (err) {
      setInsightError(`AI 서버 연결 실패: ${err.message}`)
    }
  }

  return (
    <PageShell>
      <div className="mp-eyebrow-row">
        <div className="mp-index-tag">자세 측정</div>
      </div>

      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginTop: 20 }}>
        <PoseCaptureCard label="정면 사진" onDetected={handleFrontDetected} />
        {/* ponytail: 측면 사진은 아직 어떤 엔드포인트로 보낼지 미정 — 콘솔 확인만 유지 */}
        <PoseCaptureCard label="측면 사진" onDetected={(landmarks) => console.log('side', landmarks)} />
      </div>

      {insightError && <p style={{ color: '#da291c' }}>{insightError}</p>}
      {insight && <p className="pcard-desc">{insight.message}</p>}
    </PageShell>
  )
}

export default PosturePage

import { useRef, useState } from 'react'
import './MainPage.css'
import Sidebar from './Sidebar.jsx'
import { usePoseLandmarker } from './components/usePoseLandmarker.js'

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
  ctx.fillStyle = '#e6432b'
  landmarks.forEach(({ x, y }) => {
    ctx.beginPath()
    ctx.arc(offsetX + x * renderedW, offsetY + y * renderedH, 4, 0, Math.PI * 2)
    ctx.fill()
  })
}

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
    <div className="pcard">
      <div className="pcard-body">
        <div className="pcard-title">{label}</div>
        <input type="file" accept="image/*" onChange={handleFile} />
        {imageUrl && (
          <div
            style={{
              position: 'relative',
              marginTop: 12,
              width: PREVIEW_WIDTH,
              height: PREVIEW_HEIGHT,
              background: '#1a1a1c',
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
  return (
    <div className="app revealed">
      <Sidebar />

      <main className="main">
        <div className="content">
          <div className="section-head">
            <div>
              <div className="section-eyebrow">POSTURE CHECK</div>
              <div className="section-title">자세 측정</div>
            </div>
          </div>

          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
            {/* ponytail: 좌표 → 백엔드 전송은 API 붙일 때 구현, 지금은 프론트 단독 인식 검증 단계 */}
            <PoseCaptureCard label="정면 사진" onDetected={(landmarks) => console.log('front', landmarks)} />
            <PoseCaptureCard label="측면 사진" onDetected={(landmarks) => console.log('side', landmarks)} />
          </div>
        </div>
      </main>
    </div>
  )
}

export default PosturePage

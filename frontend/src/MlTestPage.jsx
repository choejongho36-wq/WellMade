import { useRef, useState } from 'react'
import './MainPage.css'
import { usePoseLandmarker } from './components/usePoseLandmarker.js'

const AI_BASE = 'http://localhost:8000'

const EXERCISES = {
  squat: { label: '스쿼트', endpoint: '/ai/ml/squat/analyze' },
  lunge: { label: '런지', endpoint: '/ai/ml/lunge/analyze' },
}

// ponytail: 팀원이 학습시킨 스쿼트/런지 ML 모델이 실제로 조언을 주는지 확인하기 위한 테스트 전용 페이지
function MlTestPage() {
  const [exercise, setExercise] = useState('squat')
  const [imageUrl, setImageUrl] = useState(null)
  const [status, setStatus] = useState('')
  const [result, setResult] = useState(null)
  const imgRef = useRef(null)
  const { detectPose, loading } = usePoseLandmarker()

  const handleFile = (e) => {
    const file = e.target.files[0]
    if (!file) return
    setImageUrl(URL.createObjectURL(file))
    setResult(null)
    setStatus('')
  }

  const handleImageLoad = async () => {
    const landmarks = await detectPose(imgRef.current)
    if (!landmarks) {
      setStatus('관절을 인식하지 못했어요. 다른 사진으로 시도해주세요.')
      return
    }

    try {
      const res = await fetch(`${AI_BASE}${EXERCISES[exercise].endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ landmarks }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setResult(await res.json())
      setStatus('')
    } catch (err) {
      setStatus(`AI 서버 연결 실패: ${err.message}`)
    }
  }

  return (
    <div className="app revealed">
      <main className="main">
        <div className="content">
          <div className="section-head">
            <div>
              <div className="section-eyebrow">ML TEST</div>
              <div className="section-title">스쿼트/런지 ML 조언 테스트</div>
            </div>
          </div>

          <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
            {Object.entries(EXERCISES).map(([key, { label }]) => (
              <button
                key={key}
                onClick={() => {
                  setExercise(key)
                  setResult(null)
                  setStatus('')
                }}
                style={{
                  padding: '8px 16px',
                  borderRadius: 6,
                  border: '1px solid #444',
                  background: exercise === key ? '#e6432b' : 'transparent',
                  color: '#fff',
                  cursor: 'pointer',
                }}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="pcard" style={{ maxWidth: 480 }}>
            <div className="pcard-body">
              <div className="pcard-title">{EXERCISES[exercise].label} 사진</div>
              <input type="file" accept="image/*" onChange={handleFile} />
              {imageUrl && (
                <img
                  ref={imgRef}
                  src={imageUrl}
                  alt="분석 대상"
                  onLoad={handleImageLoad}
                  style={{ width: '100%', marginTop: 12, borderRadius: 8 }}
                />
              )}
              <p className="pcard-desc">{loading ? '분석 중...' : status}</p>

              {result && (
                <div style={{ marginTop: 12, lineHeight: 1.6 }}>
                  <div>모델: {result.model_name}</div>
                  <div>정상 여부: {result.is_normal ? '정상' : '이상'}</div>
                  <div>정상 확률: {(result.correct_probability * 100).toFixed(1)}%</div>
                  {'label_name' in result && <div>판정 라벨: {result.label_name}</div>}
                  {result.coaching_message && <div>코칭 문구: {result.coaching_message}</div>}
                </div>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}

export default MlTestPage

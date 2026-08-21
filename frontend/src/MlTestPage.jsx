import { useRef, useState } from 'react'
import './MainPage.css'
import { usePoseLandmarker } from './components/usePoseLandmarker.js'

const AI_BASE = 'http://localhost:8000'

const EXERCISES = {
  squat: { label: '스쿼트' },
  lunge: { label: '런지' },
}

// 2026-08-21: 원래 이 페이지는 팀원이 학습시킨 스쿼트/런지 ML 모델(HistGradientBoosting 등)을
// 테스트하는 용도였다. 실제 사진 테스트에서 정상 자세도 "발뒤꿈치 뜸"/"무릎 모임"으로 자주
// 오탐하는 신뢰도 문제가 확인됐고(원인: train/serve skew + 측면 촬영만으로는 무릎 모임/좌우
// 비대칭 같은 좌우(관상면) 판단이 애초에 불가능한 구조적 한계 — 자세한 배경은
// ai/app/pose/rules.py, claude/wellmade-ai-progress.md 참고), ML 모델은 전부 삭제하고
// 카메라 전제를 "측면 단독"에서 "측면 + 정면 듀얼"로 바꾼 규칙기반 판정으로 완전히
// 대체했다. 이 페이지도 같은 이유로 ML 모드를 없애고, /ai/pose/analyze 하나에 측면 사진과
// 정면 사진을 동시에 보내 규칙기반 판정 전체(무릎/엉덩이/어깨/발뒤꿈치 + 무릎 모임/좌우
// 비대칭)를 한 번에 확인하는 용도로 재구성했다.
function MlTestPage() {
  const [exercise, setExercise] = useState('squat')
  const [sideImageUrl, setSideImageUrl] = useState(null)
  const [frontImageUrl, setFrontImageUrl] = useState(null)
  const [sideLandmarks, setSideLandmarks] = useState(null)
  const [frontLandmarks, setFrontLandmarks] = useState(null)
  const [status, setStatus] = useState('')
  const [result, setResult] = useState(null)
  const sideImgRef = useRef(null)
  const frontImgRef = useRef(null)
  const { detectPose, loading } = usePoseLandmarker()

  const handleFile = (which) => (e) => {
    const file = e.target.files[0]
    if (!file) return
    const url = URL.createObjectURL(file)
    if (which === 'side') {
      setSideImageUrl(url)
      setSideLandmarks(null)
    } else {
      setFrontImageUrl(url)
      setFrontLandmarks(null)
    }
    setResult(null)
    setStatus('')
  }

  const handleSideImageLoad = async () => {
    const landmarks = await detectPose(sideImgRef.current)
    if (!landmarks) {
      setStatus('측면 사진에서 관절을 인식하지 못했어요. 다른 사진으로 시도해주세요.')
      return
    }
    setSideLandmarks(landmarks)
    setStatus('')
  }

  const handleFrontImageLoad = async () => {
    const landmarks = await detectPose(frontImgRef.current)
    if (!landmarks) {
      setStatus('정면 사진에서 관절을 인식하지 못했어요. 다른 사진으로 시도해주세요.')
      return
    }
    setFrontLandmarks(landmarks)
    setStatus('')
  }

  const handleAnalyze = async () => {
    if (!sideLandmarks) {
      setStatus('측면 사진을 먼저 업로드해주세요.')
      return
    }
    // 정면 사진은 선택 입력이다 — 없으면 무릎 모임/좌우 비대칭 검사만 건너뛰고 나머지
    // (무릎/엉덩이/어깨/발뒤꿈치)는 그대로 판정한다(app/schemas.py의 front_landmarks 참고).
    const body = {
      landmarks: sideLandmarks,
      exercise_type: exercise,
      ...(frontLandmarks ? { front_landmarks: frontLandmarks } : {}),
    }

    try {
      const res = await fetch(`${AI_BASE}/ai/pose/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
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
              <div className="section-eyebrow">POSE TEST</div>
              <div className="section-title">스쿼트/런지 규칙기반 판정 테스트 (측면+정면)</div>
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

          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
            <div className="pcard" style={{ maxWidth: 320, flex: '1 1 280px' }}>
              <div className="pcard-body">
                <div className="pcard-title">측면 사진 (필수)</div>
                <input type="file" accept="image/*" onChange={handleFile('side')} />
                {sideImageUrl && (
                  <img
                    ref={sideImgRef}
                    src={sideImageUrl}
                    alt="측면 분석 대상"
                    onLoad={handleSideImageLoad}
                    style={{ width: '100%', marginTop: 12, borderRadius: 8 }}
                  />
                )}
                <p className="pcard-desc" style={{ marginTop: 8 }}>
                  {sideLandmarks ? '관절 인식 완료 ✓' : '무릎/엉덩이/어깨/발뒤꿈치 판정에 쓰여요.'}
                </p>
              </div>
            </div>

            <div className="pcard" style={{ maxWidth: 320, flex: '1 1 280px' }}>
              <div className="pcard-body">
                <div className="pcard-title">정면 사진 (선택)</div>
                <input type="file" accept="image/*" onChange={handleFile('front')} />
                {frontImageUrl && (
                  <img
                    ref={frontImgRef}
                    src={frontImageUrl}
                    alt="정면 분석 대상"
                    onLoad={handleFrontImageLoad}
                    style={{ width: '100%', marginTop: 12, borderRadius: 8 }}
                  />
                )}
                <p className="pcard-desc" style={{ marginTop: 8 }}>
                  {frontLandmarks
                    ? '관절 인식 완료 ✓'
                    : '무릎 모임/좌우 비대칭 판정에 쓰여요. 없어도 나머지는 판정돼요.'}
                </p>
              </div>
            </div>
          </div>

          <button
            onClick={handleAnalyze}
            disabled={!sideLandmarks || loading}
            style={{
              marginTop: 16,
              padding: '10px 20px',
              borderRadius: 6,
              border: 'none',
              background: !sideLandmarks || loading ? '#555' : '#2b7de6',
              color: '#fff',
              cursor: !sideLandmarks || loading ? 'not-allowed' : 'pointer',
            }}
          >
            {loading ? '분석 중...' : '규칙기반 판정 실행'}
          </button>

          {status && <p className="pcard-desc" style={{ marginTop: 12 }}>{status}</p>}

          {result && (
            <div className="pcard" style={{ maxWidth: 480, marginTop: 16 }}>
              <div className="pcard-body">
                <div>정상 여부: {result.is_normal ? '정상' : '이상'}</div>
                <div>신뢰도: {(result.confidence * 100).toFixed(1)}%</div>
                {result.issues && result.issues.length > 0 ? (
                  <div style={{ marginTop: 8, lineHeight: 1.6 }}>
                    {result.issues.map((issue, i) => (
                      <div key={i}>
                        [{issue.part}] {issue.message}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div style={{ marginTop: 8, opacity: 0.8 }}>이슈 없음</div>
                )}
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}

export default MlTestPage

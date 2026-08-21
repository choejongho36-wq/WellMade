import { useRef, useState } from 'react'
import './MainPage.css'
import { usePoseLandmarker } from './components/usePoseLandmarker.js'

const AI_BASE = 'http://localhost:8000'

const EXERCISES = {
  squat: { label: '스쿼트' },
  lunge: { label: '런지' },
}

// AI 서버(app/pose/angles.py)가 각도 계산에 실제로 쓰는 관절 인덱스와 동일하게 맞춤.
// 여기 없는 나머지 랜드마크(손가락/얼굴 세부 등)는 옅은 점으로만 표시한다.
const KEY_LANDMARKS = {
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
  leftHeel: 29,
  rightHeel: 30,
  leftFootIndex: 31,
  rightFootIndex: 32,
}

// app/pose/rules.py가 각도를 계산할 때 실제로 잇는 관절 쌍 (귀-어깨-엉덩이-무릎-발목-뒤꿈치/발끝)
const SKELETON_CONNECTIONS = [
  ['leftEar', 'leftShoulder'],
  ['rightEar', 'rightShoulder'],
  ['leftShoulder', 'leftHip'],
  ['rightShoulder', 'rightHip'],
  ['leftHip', 'leftKnee'],
  ['rightHip', 'rightKnee'],
  ['leftKnee', 'leftAnkle'],
  ['rightKnee', 'rightAnkle'],
  ['leftAnkle', 'leftHeel'],
  ['rightAnkle', 'rightHeel'],
  ['leftAnkle', 'leftFootIndex'],
  ['rightAnkle', 'rightFootIndex'],
]

const LEFT_COLOR = '#00e5ff' // 왼쪽 관절 = 시안
const RIGHT_COLOR = '#ff3df0' // 오른쪽 관절 = 마젠타

// 2026-08-21: "좌표가 어디 찍히는지 보여달라"는 요청에 따라 추가.
// MediaPipe가 반환한 33개 랜드마크를 업로드한 사진 위에 그대로 그려서, 각도 계산에 실제로
// 쓰이는 값이 어느 지점을 찍은 건지 눈으로 바로 확인할 수 있게 했다. 특히 왼쪽/오른쪽을
// 색으로 구분해두면 "카메라가 완전한 측면이 아니라 사선"인 경우 양쪽 다리 점이 겹치지 않고
// 벌어져 보이므로, 사선 촬영 여부를 눈으로 바로 진단할 수 있다.
function drawLandmarks(imgEl, canvasEl, landmarks) {
  if (!imgEl || !canvasEl || !landmarks) return
  const width = imgEl.clientWidth
  const height = imgEl.clientHeight
  if (!width || !height) return
  canvasEl.width = width
  canvasEl.height = height
  const ctx = canvasEl.getContext('2d')
  ctx.clearRect(0, 0, width, height)

  // 1) 각도 계산에 쓰이지 않는 나머지 랜드마크는 옅은 흰 점으로만 표시 (전체 33개 참고용)
  landmarks.forEach((lm) => {
    ctx.beginPath()
    ctx.arc(lm.x * width, lm.y * height, 2, 0, Math.PI * 2)
    ctx.fillStyle = 'rgba(255,255,255,0.35)'
    ctx.fill()
  })

  // 2) 각도 계산에 쓰이는 관절끼리 선으로 연결 (왼쪽=시안, 오른쪽=마젠타)
  ctx.lineWidth = 2
  SKELETON_CONNECTIONS.forEach(([a, b]) => {
    const pa = landmarks[KEY_LANDMARKS[a]]
    const pb = landmarks[KEY_LANDMARKS[b]]
    if (!pa || !pb) return
    ctx.strokeStyle = a.startsWith('left') ? LEFT_COLOR : RIGHT_COLOR
    ctx.beginPath()
    ctx.moveTo(pa.x * width, pa.y * height)
    ctx.lineTo(pb.x * width, pb.y * height)
    ctx.stroke()
  })

  // 3) 핵심 관절은 크고 색 있는 점 + 라벨로 표시. visibility가 낮으면(가려짐 등) 반투명 처리해서
  //    "이 점은 신뢰도가 낮다"는 걸 바로 알 수 있게 했다.
  ctx.font = '11px sans-serif'
  Object.entries(KEY_LANDMARKS).forEach(([name, idx]) => {
    const lm = landmarks[idx]
    if (!lm) return
    const x = lm.x * width
    const y = lm.y * height
    const visibility = lm.visibility ?? 1
    const color = name.startsWith('left') ? LEFT_COLOR : RIGHT_COLOR

    ctx.globalAlpha = Math.max(visibility, 0.25)
    ctx.beginPath()
    ctx.arc(x, y, 5, 0, Math.PI * 2)
    ctx.fillStyle = color
    ctx.fill()
    ctx.strokeStyle = '#000'
    ctx.lineWidth = 1
    ctx.stroke()
    ctx.globalAlpha = 1

    // 낮은 visibility(가려짐 추정)는 라벨에 "?"를 붙여 눈에 띄게 표시
    const suffix = visibility < 0.5 ? ' ?' : ''
    ctx.fillStyle = '#fff'
    ctx.strokeStyle = '#000'
    ctx.lineWidth = 3
    ctx.strokeText(name + suffix, x + 7, y - 7)
    ctx.fillText(name + suffix, x + 7, y - 7)
  })
}

// 아래 두 함수(calculateAngle, computeSideDebugInfo)는 app/pose/angles.py의
// calculate_angle()/_select_side()를 프론트에서 그대로 재현한 것이다(2026-08-21 추가).
//
// 왜 필요한가?
// AI 서버 응답(/ai/pose/analyze)은 최종 판정 결과(is_normal/confidence/issues)만 돌려주고,
// "실제로 왼쪽/오른쪽 중 어느 다리를 골랐는지", "그 선택이 왜 그렇게 됐는지"는 알려주지
// 않는다. 그런데 측면 촬영에서 몸통에 가려 반대쪽 다리의 관절(특히 무릎) 하나만 인식이
// 불안정해도, _select_side()가 "엉덩이+무릎+발목 3곳 평균 신뢰도"로 좌우를 고르기 때문에
// 그 무릎 하나가 낮아도 나머지 두 곳(엉덩이/발목)이 잘 보이면 여전히 그 다리가 선택될 수
// 있다 — 이 경우 계산에 쓰이는 무릎 좌표 자체가 부정확해서 각도가 실제 자세와 다르게 나올
// 수 있다. 이걸 눈으로 직접 확인할 수 있도록, 좌우 각각의 신뢰도 평균과 각도를 모두
// 계산해서 화면에 함께 보여준다.
function calculateAngle(a, b, c) {
  const ba = { x: a.x - b.x, y: a.y - b.y }
  const bc = { x: c.x - b.x, y: c.y - b.y }
  const magBa = Math.hypot(ba.x, ba.y)
  const magBc = Math.hypot(bc.x, bc.y)
  if (magBa === 0 || magBc === 0) return 0
  const dot = ba.x * bc.x + ba.y * bc.y
  let cos = dot / (magBa * magBc)
  cos = Math.max(-1, Math.min(1, cos))
  return (Math.acos(cos) * 180) / Math.PI
}

function computeSideDebugInfo(landmarks) {
  const li = KEY_LANDMARKS
  const avg = (a, b, c) => (a.visibility + b.visibility + c.visibility) / 3
  const leftScore = avg(landmarks[li.leftHip], landmarks[li.leftKnee], landmarks[li.leftAnkle])
  const rightScore = avg(landmarks[li.rightHip], landmarks[li.rightKnee], landmarks[li.rightAnkle])
  // app/pose/angles.py의 _select_side()와 동일한 규칙: 왼쪽 점수가 오른쪽 이상이면 왼쪽
  const chosenSide = leftScore >= rightScore ? 'left' : 'right'

  const kneeAngle = (side) =>
    calculateAngle(landmarks[li[`${side}Hip`]], landmarks[li[`${side}Knee`]], landmarks[li[`${side}Ankle`]])
  const hipAngle = (side) =>
    calculateAngle(landmarks[li[`${side}Shoulder`]], landmarks[li[`${side}Hip`]], landmarks[li[`${side}Knee`]])

  return {
    chosenSide,
    leftScore,
    rightScore,
    left: {
      hipVis: landmarks[li.leftHip].visibility,
      kneeVis: landmarks[li.leftKnee].visibility,
      ankleVis: landmarks[li.leftAnkle].visibility,
      kneeAngle: kneeAngle('left'),
      hipAngle: hipAngle('left'),
    },
    right: {
      hipVis: landmarks[li.rightHip].visibility,
      kneeVis: landmarks[li.rightKnee].visibility,
      ankleVis: landmarks[li.rightAnkle].visibility,
      kneeAngle: kneeAngle('right'),
      hipAngle: hipAngle('right'),
    },
  }
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
  const [sideDebug, setSideDebug] = useState(null)
  const [status, setStatus] = useState('')
  const [result, setResult] = useState(null)
  const sideImgRef = useRef(null)
  const frontImgRef = useRef(null)
  const sideCanvasRef = useRef(null)
  const frontCanvasRef = useRef(null)
  const { detectPose, loading } = usePoseLandmarker()

  const handleFile = (which) => (e) => {
    const file = e.target.files[0]
    if (!file) return
    const url = URL.createObjectURL(file)
    if (which === 'side') {
      setSideImageUrl(url)
      setSideLandmarks(null)
      setSideDebug(null)
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
    setSideDebug(computeSideDebugInfo(landmarks))
    setStatus('')
    // onLoad 시점엔 이미지가 막 배치돼 clientWidth가 아직 0일 수 있어 다음 페인트 이후로 미룸
    requestAnimationFrame(() => drawLandmarks(sideImgRef.current, sideCanvasRef.current, landmarks))
  }

  const handleFrontImageLoad = async () => {
    const landmarks = await detectPose(frontImgRef.current)
    if (!landmarks) {
      setStatus('정면 사진에서 관절을 인식하지 못했어요. 다른 사진으로 시도해주세요.')
      return
    }
    setFrontLandmarks(landmarks)
    setStatus('')
    requestAnimationFrame(() => drawLandmarks(frontImgRef.current, frontCanvasRef.current, landmarks))
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

          <p className="pcard-desc" style={{ marginBottom: 12 }}>
            <span style={{ color: LEFT_COLOR }}>●</span> 왼쪽 관절&nbsp;&nbsp;
            <span style={{ color: RIGHT_COLOR }}>●</span> 오른쪽 관절&nbsp;&nbsp;
            (점 옆에 "?"가 붙으면 인식 신뢰도가 낮은 관절이에요 — 가려졌을 가능성)
          </p>

          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
            <div className="pcard" style={{ maxWidth: 320, flex: '1 1 280px' }}>
              <div className="pcard-body">
                <div className="pcard-title">측면 사진 (필수)</div>
                <input type="file" accept="image/*" onChange={handleFile('side')} />
                {sideImageUrl && (
                  <div style={{ position: 'relative', marginTop: 12 }}>
                    <img
                      ref={sideImgRef}
                      src={sideImageUrl}
                      alt="측면 분석 대상"
                      onLoad={handleSideImageLoad}
                      style={{ width: '100%', display: 'block', borderRadius: 8 }}
                    />
                    <canvas
                      ref={sideCanvasRef}
                      style={{
                        position: 'absolute',
                        top: 0,
                        left: 0,
                        width: '100%',
                        height: '100%',
                        pointerEvents: 'none',
                      }}
                    />
                  </div>
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
                  <div style={{ position: 'relative', marginTop: 12 }}>
                    <img
                      ref={frontImgRef}
                      src={frontImageUrl}
                      alt="정면 분석 대상"
                      onLoad={handleFrontImageLoad}
                      style={{ width: '100%', display: 'block', borderRadius: 8 }}
                    />
                    <canvas
                      ref={frontCanvasRef}
                      style={{
                        position: 'absolute',
                        top: 0,
                        left: 0,
                        width: '100%',
                        height: '100%',
                        pointerEvents: 'none',
                      }}
                    />
                  </div>
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

          {sideDebug && (
            <div className="pcard" style={{ maxWidth: 480, marginTop: 16 }}>
              <div className="pcard-body">
                <div className="pcard-title">
                  디버그: 좌우 다리 선택 정보 (측면 사진 기준)
                </div>
                <p className="pcard-desc" style={{ marginTop: 4, marginBottom: 8 }}>
                  AI가 실제로 고른 다리:{' '}
                  <strong style={{ color: sideDebug.chosenSide === 'left' ? LEFT_COLOR : RIGHT_COLOR }}>
                    {sideDebug.chosenSide === 'left' ? '왼쪽' : '오른쪽'}
                  </strong>{' '}
                  (엉덩이+무릎+발목 평균 신뢰도: 왼쪽 {(sideDebug.leftScore * 100).toFixed(0)}% vs 오른쪽{' '}
                  {(sideDebug.rightScore * 100).toFixed(0)}%)
                </p>
                <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ textAlign: 'left', opacity: 0.7 }}>
                      <th></th>
                      <th style={{ color: LEFT_COLOR }}>왼쪽</th>
                      <th style={{ color: RIGHT_COLOR }}>오른쪽</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>엉덩이 인식 신뢰도</td>
                      <td>{(sideDebug.left.hipVis * 100).toFixed(0)}%</td>
                      <td>{(sideDebug.right.hipVis * 100).toFixed(0)}%</td>
                    </tr>
                    <tr>
                      <td>무릎 인식 신뢰도</td>
                      <td>{(sideDebug.left.kneeVis * 100).toFixed(0)}%</td>
                      <td>{(sideDebug.right.kneeVis * 100).toFixed(0)}%</td>
                    </tr>
                    <tr>
                      <td>발목 인식 신뢰도</td>
                      <td>{(sideDebug.left.ankleVis * 100).toFixed(0)}%</td>
                      <td>{(sideDebug.right.ankleVis * 100).toFixed(0)}%</td>
                    </tr>
                    <tr>
                      <td>이 다리로 계산한 무릎 각도</td>
                      <td>{sideDebug.left.kneeAngle.toFixed(1)}도</td>
                      <td>{sideDebug.right.kneeAngle.toFixed(1)}도</td>
                    </tr>
                    <tr>
                      <td>이 다리로 계산한 엉덩이 각도</td>
                      <td>{sideDebug.left.hipAngle.toFixed(1)}도</td>
                      <td>{sideDebug.right.hipAngle.toFixed(1)}도</td>
                    </tr>
                  </tbody>
                </table>
                <p className="pcard-desc" style={{ marginTop: 8 }}>
                  실제 AI 서버 판정({exercise === 'squat' ? '무릎 50~100도/엉덩이 45~100도' : '무릎 75~105도'})은
                  위에서 "AI가 고른 다리" 쪽 각도로 계산됩니다. 반대쪽 다리 각도가 더 정상 범위에 가깝다면,
                  좌우 선택 로직이 잘못된 다리를 골랐을 가능성이 커요.
                </p>
              </div>
            </div>
          )}

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

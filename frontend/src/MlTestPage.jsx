import { useRef, useState } from 'react'
import './MainPage.css'
import { usePoseLandmarker } from './components/usePoseLandmarker.js'

const AI_BASE = 'http://localhost:8000'

// 2026-08-24: 사용자 요청에 따라 런지 지원을 제거했다(스쿼트만 지원) — 백엔드
// schemas.py의 ExerciseType도 함께 "squat" 하나만 남도록 좁혔다.
const EXERCISES = {
  squat: { label: '스쿼트' },
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

// 2026-08-24 추가 — 등 굽음(척추 굴곡) 판정을 이 페이지에서 실제로 테스트해볼 수 있게
// 캘리브레이션 값(standing_hip_angle/max_flex_hip_angle/standing_shoulder_hip_ratio)을
// 계산하는 헬퍼. 사용자가 "등굽음을 판별해내지 못해"라고 재보고해서 원인을 다시 짚어보니,
// 이 페이지가 hip_calibration 자체를 한 번도 보낸 적이 없어서(요청 body에 필드가 아예
// 없음) 등 굽음 검사가 설계상 항상 건너뛰어지고 있었다(app/pose/rules.py의
// BACK_ROUNDING_RATIO_THRESHOLD 주석 참고 — 기준값이 없으면 검사 자체를 안 함). 이 값은
// 서버가 아니라 "무거운 연산은 클라이언트" 원칙에 따라 프론트가 직접 계산해서 보낸다 —
// 아래 세 함수는 app/pose/angles.py의 calculate_angle()/_select_side()/get_hip_angle()/
// get_torso_length_ratio()를 JS로 그대로 재현한 것이다.
const MIN_RELIABLE_FOOT_LENGTH = 0.03 // app/pose/angles.py와 동일한 값(주석도 그쪽 참고)

function calculateAngle(a, b, c) {
  const ba = [a.x - b.x, a.y - b.y]
  const bc = [c.x - b.x, c.y - b.y]
  const magBa = Math.hypot(...ba)
  const magBc = Math.hypot(...bc)
  if (magBa === 0 || magBc === 0) return 0
  const dot = ba[0] * bc[0] + ba[1] * bc[1]
  const cos = Math.max(-1, Math.min(1, dot / (magBa * magBc)))
  return (Math.acos(cos) * 180) / Math.PI
}

// side="auto" 로직 재현 — 엉덩이/무릎/발목 평균 visibility가 더 높은 쪽을 고른다.
function selectSide(landmarks) {
  const leftScore =
    ((landmarks[23].visibility ?? 1) + (landmarks[25].visibility ?? 1) + (landmarks[27].visibility ?? 1)) / 3
  const rightScore =
    ((landmarks[24].visibility ?? 1) + (landmarks[26].visibility ?? 1) + (landmarks[28].visibility ?? 1)) / 3
  return leftScore >= rightScore ? 'left' : 'right'
}

// get_hip_angle() 재현 — 캘리브레이션 사진(서 있는 자세/최대한 숙인 자세)의 hip_angle을 구한다.
function computeHipAngle(landmarks) {
  const side = selectSide(landmarks)
  const [shoulderIdx, hipIdx, kneeIdx] = side === 'left' ? [11, 23, 25] : [12, 24, 26]
  return calculateAngle(landmarks[shoulderIdx], landmarks[hipIdx], landmarks[kneeIdx])
}

// get_torso_length_ratio() 재현 — 어깨-엉덩이 직선거리 / 발 길이. foot_length가 너무
// 작으면(신뢰 불가) null을 반환해, 호출부가 이 값만 빼고 캘리브레이션을 보내도록 한다
// (백엔드는 이 경우 999.0을 반환하지만, 프론트는 애초에 안 보내는 쪽을 택함 — 어차피
// standing_shoulder_hip_ratio는 선택 필드라 아예 생략해도 나머지 캘리브레이션은 정상 동작).
function computeTorsoLengthRatio(landmarks) {
  const side = selectSide(landmarks)
  const [shoulderIdx, hipIdx, ankleIdx, toeIdx] = side === 'left' ? [11, 23, 27, 31] : [12, 24, 28, 32]
  const shoulder = landmarks[shoulderIdx]
  const hip = landmarks[hipIdx]
  const ankle = landmarks[ankleIdx]
  const toe = landmarks[toeIdx]
  const footLength = Math.abs(ankle.x - toe.x)
  if (footLength < MIN_RELIABLE_FOOT_LENGTH) return null
  const torsoLength = Math.hypot(shoulder.x - hip.x, shoulder.y - hip.y)
  return torsoLength / footLength
}

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
  const sideCanvasRef = useRef(null)
  const frontCanvasRef = useRef(null)
  const { detectPose, loading } = usePoseLandmarker()

  // 캘리브레이션(2026-08-24 추가) — 등 굽음(back_rounded) 판정을 이 페이지에서 실제로
  // 테스트해보려면 hip_calibration을 보내야 하는데, standing_hip_angle/max_flex_hip_angle이
  // 둘 다 필수 필드(app/schemas.py의 HipFlexibilityCalibration 참고)라 사진 두 장이 필요하다.
  const [calibStandingUrl, setCalibStandingUrl] = useState(null)
  const [calibMaxFlexUrl, setCalibMaxFlexUrl] = useState(null)
  const [calibStandingHipAngle, setCalibStandingHipAngle] = useState(null)
  const [calibStandingRatio, setCalibStandingRatio] = useState(null)
  const [calibMaxFlexHipAngle, setCalibMaxFlexHipAngle] = useState(null)
  const calibStandingImgRef = useRef(null)
  const calibMaxFlexImgRef = useRef(null)

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

  const handleCalibFile = (which) => (e) => {
    const file = e.target.files[0]
    if (!file) return
    const url = URL.createObjectURL(file)
    if (which === 'standing') {
      setCalibStandingUrl(url)
      setCalibStandingHipAngle(null)
      setCalibStandingRatio(null)
    } else {
      setCalibMaxFlexUrl(url)
      setCalibMaxFlexHipAngle(null)
    }
    setResult(null)
    setStatus('')
  }

  const handleCalibStandingLoad = async () => {
    const landmarks = await detectPose(calibStandingImgRef.current)
    if (!landmarks) {
      setStatus('캘리브레이션(선 자세) 사진에서 관절을 인식하지 못했어요. 다른 사진으로 시도해주세요.')
      return
    }
    setCalibStandingHipAngle(computeHipAngle(landmarks))
    setCalibStandingRatio(computeTorsoLengthRatio(landmarks))
    setStatus('')
  }

  const handleCalibMaxFlexLoad = async () => {
    const landmarks = await detectPose(calibMaxFlexImgRef.current)
    if (!landmarks) {
      setStatus('캘리브레이션(최대한 숙인 자세) 사진에서 관절을 인식하지 못했어요. 다른 사진으로 시도해주세요.')
      return
    }
    setCalibMaxFlexHipAngle(computeHipAngle(landmarks))
    setStatus('')
  }

  const handleAnalyze = async () => {
    if (!sideLandmarks) {
      setStatus('측면 사진을 먼저 업로드해주세요.')
      return
    }
    // 정면 사진은 선택 입력이다 — 없으면 무릎 모임/좌우 비대칭 검사만 건너뛰고 나머지
    // (무릎/엉덩이/어깨/발뒤꿈치)는 그대로 판정한다(app/schemas.py의 front_landmarks 참고).
    //
    // hip_calibration은 두 캘리브레이션 사진(선 자세 + 최대한 숙인 자세)이 모두 인식됐을
    // 때만 보낸다 — standing_hip_angle/max_flex_hip_angle 둘 다 스키마 필수 필드라 하나만
    // 있으면 아예 안 보내는 쪽을 택했다(하나만 채워 보내면 422 에러). 이걸 보내야만 등
    // 굽음(back_rounded) 검사가 실제로 동작한다 — standing_shoulder_hip_ratio 없이는
    // 기준값이 없어 이 검사가 항상 건너뛰어짐(app/pose/rules.py 주석 참고).
    const hasFullCalibration = calibStandingHipAngle != null && calibMaxFlexHipAngle != null
    const body = {
      landmarks: sideLandmarks,
      exercise_type: exercise,
      ...(frontLandmarks ? { front_landmarks: frontLandmarks } : {}),
      ...(hasFullCalibration
        ? {
            hip_calibration: {
              standing_hip_angle: calibStandingHipAngle,
              max_flex_hip_angle: calibMaxFlexHipAngle,
              ...(calibStandingRatio != null ? { standing_shoulder_hip_ratio: calibStandingRatio } : {}),
            },
          }
        : {}),
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
              <div className="section-title">스쿼트 규칙기반 판정 테스트 (측면+정면)</div>
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

          <p className="pcard-desc" style={{ marginTop: 20, marginBottom: 4 }}>
            아래 두 캘리브레이션 사진을 <strong>둘 다</strong> 올리면 개인별 엉덩이 각도
            판정과 등 굽음(back_rounded) 판정에 쓰여요 — 둘 중 하나만 있으면 무시돼요
            (AI 서버가 두 값을 항상 함께 요구해서요). 없어도 나머지 판정은 그대로 동작해요.
          </p>
          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
            <div className="pcard" style={{ maxWidth: 320, flex: '1 1 280px' }}>
              <div className="pcard-body">
                <div className="pcard-title">캘리브레이션: 편하게 선 자세 (선택, 측면)</div>
                <input type="file" accept="image/*" onChange={handleCalibFile('standing')} />
                {calibStandingUrl && (
                  <img
                    ref={calibStandingImgRef}
                    src={calibStandingUrl}
                    alt="캘리브레이션: 선 자세"
                    onLoad={handleCalibStandingLoad}
                    style={{ width: '100%', display: 'block', borderRadius: 8, marginTop: 12 }}
                  />
                )}
                <p className="pcard-desc" style={{ marginTop: 8 }}>
                  {calibStandingHipAngle != null
                    ? `엉덩이 각도 ${calibStandingHipAngle.toFixed(1)}도` +
                      (calibStandingRatio != null
                        ? `, 어깨-엉덩이/발 길이 비율 ${calibStandingRatio.toFixed(3)} 인식 완료 ✓`
                        : ' 인식 완료 ✓ (발 길이가 너무 짧게 잡혀 비율은 계산 못함)')
                    : '등을 곧게 펴고 편하게 선 옆모습이어야 해요.'}
                </p>
              </div>
            </div>

            <div className="pcard" style={{ maxWidth: 320, flex: '1 1 280px' }}>
              <div className="pcard-body">
                <div className="pcard-title">캘리브레이션: 무리 없이 최대한 숙인 자세 (선택, 측면)</div>
                <input type="file" accept="image/*" onChange={handleCalibFile('maxflex')} />
                {calibMaxFlexUrl && (
                  <img
                    ref={calibMaxFlexImgRef}
                    src={calibMaxFlexUrl}
                    alt="캘리브레이션: 최대한 숙인 자세"
                    onLoad={handleCalibMaxFlexLoad}
                    style={{ width: '100%', display: 'block', borderRadius: 8, marginTop: 12 }}
                  />
                )}
                <p className="pcard-desc" style={{ marginTop: 8 }}>
                  {calibMaxFlexHipAngle != null
                    ? `엉덩이 각도 ${calibMaxFlexHipAngle.toFixed(1)}도 인식 완료 ✓`
                    : '무릎을 굽히지 않고 상체만 무리 없는 선에서 최대한 숙인 옆모습이어야 해요.'}
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
                {/* 2026-08-21 추가: 예전엔 "정상"으로 뜨면 issues가 비어 있어서 실제
                    knee_angle/hip_angle/shoulder_angle 등 원시 숫자가 화면 어디에도
                    안 보이는 문제가 있었다("정상으로 떠서인지 결과 패널 수치가 안 떠"라고
                    사용자가 직접 지적함). AI 서버 응답에 angles 필드를 새로 추가하고,
                    정상/이상과 무관하게 항상 이 원시 값을 보여주도록 했다. */}
                {result.angles && (
                  <div
                    style={{
                      marginTop: 12,
                      paddingTop: 12,
                      borderTop: '1px solid #444',
                      fontSize: 13,
                      opacity: 0.85,
                      lineHeight: 1.6,
                    }}
                  >
                    <div>무릎 각도: {result.angles.knee_angle}도</div>
                    <div>엉덩이 각도: {result.angles.hip_angle}도</div>
                    <div>
                      어깨 각도(절대, 참고용): {result.angles.shoulder_angle}도
                      {/* 2026-08-24부터 판정에는 안 쓰임 — 아래 어깨 편차 값이 실제 판정을 담당 */}
                    </div>
                    <div>
                      어깨 편차(목-상체 기울기 차이): {result.angles.shoulder_forward_lean_deg}도
                      {/* 실제 어깨 말림 판정에 쓰이는 값. 0 이하면 정상, 임계값(20도)보다
                          크면 어깨 말림으로 판정된다 — angles.py의
                          get_shoulder_forward_lean_deg 참고 */}
                    </div>
                    <div>발뒤꿈치 뜸 비율: {result.angles.heel_lift_ratio}</div>
                    <div>무릎-발끝 좌표 거리: {result.angles.knee_over_toe_ratio}</div>
                    <div>
                      어깨-엉덩이 직선거리/발 길이 비율: {result.angles.torso_length_ratio}
                      {/* 위 캘리브레이션 두 장을 모두 올려서 hip_calibration이 실제로 전송된
                          경우에만 등 굽음(back_rounded) 판정에 쓰인다 — 안 올리면 이 숫자는
                          참고용으로만 노출되고 판정에는 관여하지 않는다 (angles.py 참고) */}
                    </div>
                    {result.angles.knee_valgus_ratio !== null && (
                      <div>무릎 모임 비율: {result.angles.knee_valgus_ratio}</div>
                    )}
                    {result.angles.knee_asymmetry_deg !== null && (
                      <div>좌우 비대칭: {result.angles.knee_asymmetry_deg}도</div>
                    )}
                  </div>
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

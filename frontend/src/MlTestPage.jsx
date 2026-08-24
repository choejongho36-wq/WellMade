import { useRef, useState } from 'react'
import './MainPage.css'
import { usePoseLandmarker } from './components/usePoseLandmarker.js'

// (2026-08-24) 이 페이지는 원래 /ai/pose/analyze(AI-03, 정지 자세 1차 판정)를 호출해
// "정상/이상" 결과까지 보여주는 통합 테스트 페이지였다. 사용자가 업로드한 서비스 흐름도를
// 기준으로 "정지자세 촬영 관련 부분은 다른 팀원이 맡기로 했다"며 AI-03 자체가 백엔드에서
// 완전히 삭제되면서(ai/app/pose/rules.py의 judge_static_pose() 등), 이 페이지도 함께
// 정리했었다(라우터에서 /ml-test 제거, 파일은 _to_delete/로 이동).
//
// 이번에 다시 만드는 이 페이지는 각도/비율 "계산"만 프론트에서 순수하게 연습해보는 용도로
// 시작했다(서버 호출 없음, 아래 각도/비율 계산 함수들은 예전 ai/app/pose/angles.py 공식을
// JS로 그대로 옮긴 것 — 정확한 원본은 git 히스토리 커밋 3c1525e 이전 참고).
//
// (2026-08-24 추가) 다만 "계산된 숫자만 보고는 정상/이상을 스스로 판단하기 어렵다"는 요청에
// 따라, 판정 자체는 여전히 서버(AI-06 실시간 코칭, /ai/coaching/frame)에 맡기고 그 결과만
// 이 페이지에 보여주는 버튼을 추가했다. 이건 AI-03(정지 자세 1차 판정)을 되살리는 게
// 아니다 — AI-03과 AI-06은 서로 다른 엔드포인트였고, AI-06은 이번 삭제 대상에 전혀 포함된
// 적이 없다. AI-06은 원래 "실시간 프레임 스트림"을 전제로 설계돼 있어(judge_realtime_coaching의
// MIN_FRAMES=3 미만이면 판정을 보류하고 신뢰도만 낮게 반환) 사진 한 장으로는 그대로 호출할
// 수 없는데, 이 페이지는 같은 계산값을 가진 프레임 3개(타임스탬프만 0.1초씩 차이)를 만들어
// 보내는 방식으로 우회한다 — 값이 동일하니 기울기(변화율)가 0이 되어 서버가 "정지(holding)"
// 상태로 인식하고, 실제 NORMAL_RANGES/임계값 비교가 그대로 적용된다. 판정 로직 자체를
// 프론트에 새로 만든 게 아니라, 이미 있는 AI-06 로직을 사진 1장짜리 입력에 맞게 재사용하는
// 방식이다.
//
// (2026-08-24 추가) MediaPipe 자동 인식이 가끔 관절을 엉뚱한 위치에 잡는 경우(예: 팔에
// 가려진 엉덩이가 실제 위치가 아닌 곳에 찍히는 경우)가 있어서, 핵심 관절점(KEY_LANDMARKS —
// 계산에 실제로 쓰이는 점들)을 사진 위에서 마우스/터치로 직접 드래그해 위치를 고칠 수 있게
// 했다. 서버에는 여전히 원본 좌표를 보내지 않으므로(이 페이지는 항상 서버 호출 없이 각도만
// 계산) 백엔드 변경은 필요 없다 — 드래그로 landmarks 배열의 x/y 값만 프론트 state에서
// 바꾸고, 그 즉시 같은 랜드마크로 아래 측정값/판정 요청이 재계산된다.
const AI_BASE = 'http://localhost:8000'
const DRAG_HIT_RADIUS_PX = 16 // 이 거리(px) 안에 있는 핵심 관절점만 드래그로 잡을 수 있다.

// MediaPipe Pose 33개 관절 좌표 중 각도/비율 계산에 실제로 쓰는 인덱스.
const LEFT_SHOULDER = 11
const RIGHT_SHOULDER = 12
const LEFT_HIP = 23
const RIGHT_HIP = 24
const LEFT_KNEE = 25
const RIGHT_KNEE = 26
const LEFT_ANKLE = 27
const RIGHT_ANKLE = 28
const LEFT_HEEL = 29
const LEFT_FOOT_INDEX = 31
const RIGHT_FOOT_INDEX = 32
const LEFT_EAR = 7

// 발목-발끝 거리가 이보다 작으면(발이 카메라를 거의 정면으로 향하거나 인식 불안정) 방향
// 판단이 노이즈에 취약해져, 계산을 포기하고 안전한 기본값을 반환한다 — 예전 angles.py와
// 동일한 값/이유.
const MIN_RELIABLE_FOOT_LENGTH = 0.03

const KEY_LANDMARKS = {
  leftEar: 7,
  rightEar: 8,
  leftShoulder: LEFT_SHOULDER,
  rightShoulder: RIGHT_SHOULDER,
  leftHip: LEFT_HIP,
  rightHip: RIGHT_HIP,
  leftKnee: LEFT_KNEE,
  rightKnee: RIGHT_KNEE,
  leftAnkle: LEFT_ANKLE,
  rightAnkle: RIGHT_ANKLE,
  leftHeel: LEFT_HEEL,
  rightHeel: 30,
  leftFootIndex: LEFT_FOOT_INDEX,
  rightFootIndex: RIGHT_FOOT_INDEX,
}

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

const LEFT_COLOR = '#00e5ff'
const RIGHT_COLOR = '#ff3df0'

// ---- 각도/비율 계산 (구 ai/app/pose/angles.py 이식) ----

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

// side="auto"면 엉덩이/무릎/발목 평균 visibility가 더 높은 쪽을 고른다 — 측면 촬영에서
// 카메라 반대쪽 다리는 가려져 visibility가 낮게 잡히는 경우가 많기 때문.
function selectSide(landmarks, side = 'auto') {
  if (side === 'left' || side === 'right') return side
  const leftScore =
    ((landmarks[LEFT_HIP].visibility ?? 1) +
      (landmarks[LEFT_KNEE].visibility ?? 1) +
      (landmarks[LEFT_ANKLE].visibility ?? 1)) /
    3
  const rightScore =
    ((landmarks[RIGHT_HIP].visibility ?? 1) +
      (landmarks[RIGHT_KNEE].visibility ?? 1) +
      (landmarks[RIGHT_ANKLE].visibility ?? 1)) /
    3
  return leftScore >= rightScore ? 'left' : 'right'
}

// 엉덩이-무릎-발목 3점. 180도에 가까울수록 다리를 편 상태.
function getKneeAngle(landmarks, side = 'auto') {
  const chosen = selectSide(landmarks, side)
  const [hipIdx, kneeIdx, ankleIdx] = chosen === 'left' ? [LEFT_HIP, LEFT_KNEE, LEFT_ANKLE] : [RIGHT_HIP, RIGHT_KNEE, RIGHT_ANKLE]
  return calculateAngle(landmarks[hipIdx], landmarks[kneeIdx], landmarks[ankleIdx])
}

// 어깨-엉덩이-무릎 3점. 상체가 다리 기준으로 얼마나 숙여졌는지.
function getHipAngle(landmarks, side = 'auto') {
  const chosen = selectSide(landmarks, side)
  const [shoulderIdx, hipIdx, kneeIdx] = chosen === 'left' ? [LEFT_SHOULDER, LEFT_HIP, LEFT_KNEE] : [RIGHT_SHOULDER, RIGHT_HIP, RIGHT_KNEE]
  return calculateAngle(landmarks[shoulderIdx], landmarks[hipIdx], landmarks[kneeIdx])
}

// 귀-어깨-엉덩이 3점 절대각도(참고용) — 실제 어깨 말림 판정은 아래 shoulderForwardLeanDeg가 담당.
function getShoulderAlignmentAngle(landmarks, side = 'auto') {
  const chosen = selectSide(landmarks, side)
  const [earIdx, shoulderIdx, hipIdx] = chosen === 'left' ? [LEFT_EAR, LEFT_SHOULDER, LEFT_HIP] : [8, RIGHT_SHOULDER, RIGHT_HIP]
  return calculateAngle(landmarks[earIdx], landmarks[shoulderIdx], landmarks[hipIdx])
}

// 목 기울기 - 상체 기울기(도). 0 이하면 목이 상체만큼(또는 더) 세워진 정상 자세,
// 크게 양수면 목이 상체보다 훨씬 더 앞으로 숙여진(어깨 말림) 자세.
function getShoulderForwardLeanDeg(landmarks, side = 'auto') {
  const chosen = selectSide(landmarks, side)
  const [earIdx, shoulderIdx, hipIdx, ankleIdx, toeIdx] =
    chosen === 'left' ? [LEFT_EAR, LEFT_SHOULDER, LEFT_HIP, LEFT_ANKLE, LEFT_FOOT_INDEX] : [8, RIGHT_SHOULDER, RIGHT_HIP, RIGHT_ANKLE, RIGHT_FOOT_INDEX]
  const ear = landmarks[earIdx]
  const shoulder = landmarks[shoulderIdx]
  const hip = landmarks[hipIdx]
  const ankle = landmarks[ankleIdx]
  const toe = landmarks[toeIdx]
  const footLength = Math.abs(ankle.x - toe.x)
  if (footLength < MIN_RELIABLE_FOOT_LENGTH) return 0
  const facingDirection = toe.x - ankle.x >= 0 ? 1 : -1

  const torsoDx = (shoulder.x - hip.x) * facingDirection
  const torsoDy = shoulder.y - hip.y
  const torsoTiltDeg = (Math.atan2(torsoDx, -torsoDy) * 180) / Math.PI

  const neckDx = (ear.x - shoulder.x) * facingDirection
  const neckDy = ear.y - shoulder.y
  const neckTiltDeg = (Math.atan2(neckDx, -neckDy) * 180) / Math.PI

  return neckTiltDeg - torsoTiltDeg
}

// 발뒤꿈치-발끝 높이차 / 발 길이. 값이 클수록 발뒤꿈치가 뜬 상태.
function getHeelLiftRatio(landmarks, side = 'auto') {
  const chosen = selectSide(landmarks, side)
  const [heelIdx, toeIdx, ankleIdx] = chosen === 'left' ? [LEFT_HEEL, LEFT_FOOT_INDEX, LEFT_ANKLE] : [30, RIGHT_FOOT_INDEX, RIGHT_ANKLE]
  const heel = landmarks[heelIdx]
  const toe = landmarks[toeIdx]
  const ankle = landmarks[ankleIdx]
  const footLength = Math.abs(ankle.x - toe.x)
  if (footLength < MIN_RELIABLE_FOOT_LENGTH) return 0
  return (toe.y - heel.y) / footLength
}

// 무릎-발끝 원시 좌표 거리(발 길이 정규화 없음, facing_direction 방향 보정만 반영).
// 값이 0 이하면 무릎이 발끝을 안 넘은 상태, 클수록 많이 넘은 상태.
function getKneeOverToeRatio(landmarks, side = 'auto') {
  const chosen = selectSide(landmarks, side)
  const [kneeIdx, ankleIdx, toeIdx] = chosen === 'left' ? [LEFT_KNEE, LEFT_ANKLE, LEFT_FOOT_INDEX] : [RIGHT_KNEE, RIGHT_ANKLE, RIGHT_FOOT_INDEX]
  const knee = landmarks[kneeIdx]
  const ankle = landmarks[ankleIdx]
  const toe = landmarks[toeIdx]
  const footLength = Math.abs(ankle.x - toe.x)
  if (footLength < MIN_RELIABLE_FOOT_LENGTH) return 0
  const facingDirection = toe.x - ankle.x >= 0 ? 1 : -1
  return (knee.x - toe.x) * facingDirection
}

// 어깨-엉덩이 직선거리 / 발 길이. 등이 곧게 펴져 있으면 척추 길이에 가깝게, 둥글게
// 말리면(등 굽음) 짧아진다. 값이 작을수록 등이 굽은 쪽 — 기준치 없이 이 값 하나만으로는
// "얼마나 작아야 이상인지" 판단할 수 없어(체형마다 다름), 여기서는 원시 값만 보여준다.
function getTorsoLengthRatio(landmarks, side = 'auto') {
  const chosen = selectSide(landmarks, side)
  const [shoulderIdx, hipIdx, ankleIdx, toeIdx] =
    chosen === 'left' ? [LEFT_SHOULDER, LEFT_HIP, LEFT_ANKLE, LEFT_FOOT_INDEX] : [RIGHT_SHOULDER, RIGHT_HIP, RIGHT_ANKLE, RIGHT_FOOT_INDEX]
  const shoulder = landmarks[shoulderIdx]
  const hip = landmarks[hipIdx]
  const ankle = landmarks[ankleIdx]
  const toe = landmarks[toeIdx]
  const footLength = Math.abs(ankle.x - toe.x)
  if (footLength < MIN_RELIABLE_FOOT_LENGTH) return null
  const torsoLength = Math.hypot(shoulder.x - hip.x, shoulder.y - hip.y)
  return torsoLength / footLength
}

// ---- 정면 촬영 전용(무릎 모임/좌우 비대칭) ----

// 무릎 사이 너비 / 발목 사이 너비. 1.0 이상이면 정상, 작을수록 무릎이 안쪽으로 모인(valgus) 상태.
function getKneeValgusRatio(frontLandmarks) {
  const kneeWidth = Math.abs(frontLandmarks[RIGHT_KNEE].x - frontLandmarks[LEFT_KNEE].x)
  const ankleWidth = Math.abs(frontLandmarks[RIGHT_ANKLE].x - frontLandmarks[LEFT_ANKLE].x)
  if (ankleWidth === 0) return 1
  return kneeWidth / ankleWidth
}

// 좌우 무릎 굽힘 각도 차이(도, 절대값). 0에 가까울수록 대칭.
function getKneeLrAsymmetryDeg(frontLandmarks) {
  const leftAngle = calculateAngle(frontLandmarks[LEFT_HIP], frontLandmarks[LEFT_KNEE], frontLandmarks[LEFT_ANKLE])
  const rightAngle = calculateAngle(frontLandmarks[RIGHT_HIP], frontLandmarks[RIGHT_KNEE], frontLandmarks[RIGHT_ANKLE])
  return Math.abs(leftAngle - rightAngle)
}

// 좌우 두 점을 잇는 선이 수평선과 이루는 각도(도), 부호 있게. 양수=왼쪽이 더 높음.
// AI-15(동년배 비교 인사이트)가 서버에서 계산하는 값과 동일한 공식 — 이 페이지에서는
// 그 API를 호출하지 않고 프론트에서 미리 값만 확인해보는 용도.
function horizontalTiltAngle(leftPoint, rightPoint) {
  const dx = rightPoint.x - leftPoint.x
  const dy = rightPoint.y - leftPoint.y
  if (dx === 0 && dy === 0) return 0
  return (Math.atan2(dy, dx) * 180) / Math.PI
}

function getShoulderTiltAngle(landmarks) {
  return horizontalTiltAngle(landmarks[LEFT_SHOULDER], landmarks[RIGHT_SHOULDER])
}

function getPelvisTiltAngle(landmarks) {
  return horizontalTiltAngle(landmarks[LEFT_HIP], landmarks[RIGHT_HIP])
}

// 33개 랜드마크를 사진 위에 그려서, 각도 계산에 실제로 쓰이는 지점이 어디인지 눈으로
// 바로 확인할 수 있게 한다. 왼쪽=시안/오른쪽=마젠타로 구분.
function drawLandmarks(imgEl, canvasEl, landmarks) {
  if (!imgEl || !canvasEl || !landmarks) return
  const width = imgEl.clientWidth
  const height = imgEl.clientHeight
  if (!width || !height) return
  canvasEl.width = width
  canvasEl.height = height
  const ctx = canvasEl.getContext('2d')
  ctx.clearRect(0, 0, width, height)

  landmarks.forEach((lm) => {
    ctx.beginPath()
    ctx.arc(lm.x * width, lm.y * height, 2, 0, Math.PI * 2)
    ctx.fillStyle = 'rgba(255,255,255,0.35)'
    ctx.fill()
  })

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

    const suffix = visibility < 0.5 ? ' ?' : ''
    ctx.fillStyle = '#fff'
    ctx.strokeStyle = '#000'
    ctx.lineWidth = 3
    ctx.strokeText(name + suffix, x + 7, y - 7)
    ctx.fillText(name + suffix, x + 7, y - 7)
  })
}

// 캔버스 위 포인터 좌표(px) → 정규화 좌표(0~1). 캔버스 크기가 곧 이미지 렌더 크기와
// 같으므로(letterbox 없음, PhotoCard의 <img>가 width:100%/display:block) 별도 스케일
// 보정 없이 캔버스의 실제 렌더 크기(getBoundingClientRect)만 기준으로 삼으면 된다.
function pixelToNormalized(canvasEl, clientX, clientY) {
  const rect = canvasEl.getBoundingClientRect()
  const x = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width))
  const y = Math.min(1, Math.max(0, (clientY - rect.top) / rect.height))
  return { x, y }
}

// 포인터 좌표에서 DRAG_HIT_RADIUS_PX 안에 있는 "핵심 관절"(KEY_LANDMARKS — 계산에 실제로
// 쓰이는 점) 중 가장 가까운 것을 찾는다. 33개 원본 랜드마크 전부를 드래그 대상으로 두면
// 점이 너무 촘촘해 잘못 짚기 쉬워서, 의미 있는 지점으로만 범위를 좁혔다.
function findNearestKeyLandmark(canvasEl, landmarks, clientX, clientY) {
  const rect = canvasEl.getBoundingClientRect()
  const px = clientX - rect.left
  const py = clientY - rect.top
  let closestIdx = null
  let closestDist = DRAG_HIT_RADIUS_PX
  Object.values(KEY_LANDMARKS).forEach((idx) => {
    const lm = landmarks[idx]
    if (!lm) return
    const dx = lm.x * rect.width - px
    const dy = lm.y * rect.height - py
    const dist = Math.hypot(dx, dy)
    if (dist < closestDist) {
      closestDist = dist
      closestIdx = idx
    }
  })
  return closestIdx
}

// landmarks 배열에서 index 하나의 x/y만 교체한 새 배열을 반환한다 — 리액트 state 불변성을
// 지키기 위해 원본 배열/객체는 건드리지 않는다(원본은 "되돌리기" 버튼용으로 별도 보관됨).
function withUpdatedLandmark(landmarks, index, x, y) {
  const next = landmarks.slice()
  next[index] = { ...next[index], x, y }
  return next
}

function fmt(value, digits = 1) {
  return value == null ? '측정 불가 (발 길이 너무 짧음)' : value.toFixed(digits)
}

function MeasurementPanel({ title, landmarks }) {
  if (!landmarks) return null
  return (
    <div className="pcard" style={{ maxWidth: 340, marginTop: 12 }}>
      <div className="pcard-body" style={{ fontSize: 13, lineHeight: 1.7 }}>
        <div className="pcard-title">{title}</div>
        <div>무릎 각도: {fmt(getKneeAngle(landmarks))}도</div>
        <div>엉덩이 각도: {fmt(getHipAngle(landmarks))}도</div>
        <div>어깨 각도(절대, 참고용): {fmt(getShoulderAlignmentAngle(landmarks))}도</div>
        <div>어깨 편차(목-상체 기울기 차이): {fmt(getShoulderForwardLeanDeg(landmarks))}도</div>
        <div>발뒤꿈치 뜸 비율: {fmt(getHeelLiftRatio(landmarks), 3)}</div>
        <div>무릎-발끝 좌표 거리: {fmt(getKneeOverToeRatio(landmarks), 3)}</div>
        <div>어깨-엉덩이/발 길이 비율: {fmt(getTorsoLengthRatio(landmarks), 3)}</div>
      </div>
    </div>
  )
}

function FrontalMeasurementPanel({ landmarks }) {
  if (!landmarks) return null
  return (
    <div className="pcard" style={{ maxWidth: 340, marginTop: 12 }}>
      <div className="pcard-body" style={{ fontSize: 13, lineHeight: 1.7 }}>
        <div className="pcard-title">정면 촬영 전용 측정값</div>
        <div>무릎 모임 비율: {fmt(getKneeValgusRatio(landmarks), 3)}</div>
        <div>좌우 비대칭: {fmt(getKneeLrAsymmetryDeg(landmarks))}도</div>
        <div style={{ marginTop: 8, opacity: 0.7 }}>동년배 비교 인사이트(AI-15)용 참고값</div>
        <div>어깨 좌우 기울기: {fmt(getShoulderTiltAngle(landmarks))}도</div>
        <div>골반 좌우 기울기: {fmt(getPelvisTiltAngle(landmarks))}도</div>
      </div>
    </div>
  )
}

const PART_LABELS = {
  knee: '무릎',
  hip: '엉덩이',
  shoulder: '어깨',
  heel: '발뒤꿈치',
  knee_valgus: '무릎 모임',
  asymmetry: '좌우 비대칭',
  knee_over_toe: '무릎-발끝',
  back_rounded: '등 굽음',
  movement: '움직임',
  data: '데이터',
}

// AI-06(/ai/coaching/frame)이 돌려준 판정 결과를 그대로 보여준다 — 여기서 정상/이상을
// 다시 계산하지 않는다(단일 출처 원칙: 판정은 항상 서버 응답 그대로 표시).
function JudgmentPanel({ result, error, loading }) {
  if (!loading && !error && !result) return null
  return (
    <div className="pcard" style={{ maxWidth: 340, marginTop: 12 }}>
      <div className="pcard-body" style={{ fontSize: 13, lineHeight: 1.7 }}>
        <div className="pcard-title">AI 서버 판정 결과 (AI-06)</div>
        {loading && <div>판정 요청 중...</div>}
        {error && <div style={{ color: '#e6432b' }}>{error}</div>}
        {result && (
          <>
            <div>
              정상 여부:{' '}
              <span style={{ color: result.is_normal ? '#2eb872' : '#e6432b', fontWeight: 600 }}>
                {result.is_normal ? '정상' : '이상'}
              </span>
            </div>
            <div>동작 단계: {result.phase}</div>
            <div>신뢰도: {(result.confidence * 100).toFixed(0)}%</div>
            {result.issues.length > 0 && (
              <div style={{ marginTop: 6 }}>
                {result.issues.map((issue, i) => (
                  <div key={i} style={{ marginTop: 4 }}>
                    · [{PART_LABELS[issue.part] ?? issue.part}] {issue.message}
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

function PhotoCard({
  label,
  imageUrl,
  landmarks,
  onFile,
  onImageLoad,
  imgRef,
  canvasRef,
  notReadyMessage,
  onPointerDown,
  onPointerMove,
  onPointerUp,
  onReset,
}) {
  return (
    <div className="pcard" style={{ maxWidth: 320, flex: '1 1 280px' }}>
      <div className="pcard-body">
        <div className="pcard-title">{label}</div>
        <input type="file" accept="image/*" onChange={onFile} />
        {imageUrl && (
          <div style={{ position: 'relative', marginTop: 12 }}>
            <img
              ref={imgRef}
              src={imageUrl}
              alt={label}
              onLoad={onImageLoad}
              style={{ width: '100%', display: 'block', borderRadius: 8 }}
            />
            {/* landmarks가 있을 때만 pointerEvents를 켠다 — 인식 전에는 드래그할 대상이
                없으므로 이미지 클릭/스크롤을 그대로 방해하지 않게 한다.
                touchAction: 'none'은 터치 드래그 중 화면 스크롤과 충돌하지 않게 하기 위함. */}
            <canvas
              ref={canvasRef}
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
              onPointerCancel={onPointerUp}
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                height: '100%',
                pointerEvents: landmarks ? 'auto' : 'none',
                touchAction: 'none',
                cursor: landmarks ? 'grab' : 'default',
              }}
            />
          </div>
        )}
        <p className="pcard-desc" style={{ marginTop: 8 }}>
          {landmarks
            ? '관절 인식 완료 ✓ — 위치가 이상한 점은 사진 위에서 직접 드래그해 옮길 수 있어요.'
            : notReadyMessage}
        </p>
        {landmarks && onReset && (
          <button onClick={onReset} style={{ marginTop: 6 }}>
            관절 위치 원래대로 되돌리기
          </button>
        )}
      </div>
    </div>
  )
}

function MlTestPage() {
  const [sideImageUrl, setSideImageUrl] = useState(null)
  const [frontImageUrl, setFrontImageUrl] = useState(null)
  const [sideLandmarks, setSideLandmarks] = useState(null)
  const [frontLandmarks, setFrontLandmarks] = useState(null)
  // 드래그로 고치기 전 MediaPipe 원본 인식 결과를 따로 보관 — "되돌리기" 버튼용.
  // withUpdatedLandmark는 항상 새 배열/새 객체를 만들어내므로(불변 업데이트) 이 원본은
  // 드래그로 인해 절대 변형되지 않는다.
  const [sideOriginalLandmarks, setSideOriginalLandmarks] = useState(null)
  const [frontOriginalLandmarks, setFrontOriginalLandmarks] = useState(null)
  const [status, setStatus] = useState('')
  const [judgeResult, setJudgeResult] = useState(null)
  const [judgeError, setJudgeError] = useState('')
  const [judging, setJudging] = useState(false)
  const sideImgRef = useRef(null)
  const frontImgRef = useRef(null)
  const sideCanvasRef = useRef(null)
  const frontCanvasRef = useRef(null)
  // 지금 드래그 중인 관절 정보({ which: 'side'|'front', index }) — 렌더마다 새로 만들 필요가
  // 없는 값이라 state가 아닌 ref로 관리해서 드래그 중 불필요한 리렌더를 만들지 않는다.
  const draggingRef = useRef(null)
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
    setStatus('')
  }

  const handleSideImageLoad = async () => {
    const landmarks = await detectPose(sideImgRef.current)
    if (!landmarks) {
      setStatus('측면 사진에서 관절을 인식하지 못했어요. 다른 사진으로 시도해주세요.')
      return
    }
    setSideLandmarks(landmarks)
    setSideOriginalLandmarks(landmarks)
    setStatus('')
    requestAnimationFrame(() => drawLandmarks(sideImgRef.current, sideCanvasRef.current, landmarks))
  }

  const handleFrontImageLoad = async () => {
    const landmarks = await detectPose(frontImgRef.current)
    if (!landmarks) {
      setStatus('정면 사진에서 관절을 인식하지 못했어요. 다른 사진으로 시도해주세요.')
      return
    }
    setFrontLandmarks(landmarks)
    setFrontOriginalLandmarks(landmarks)
    setStatus('')
    requestAnimationFrame(() => drawLandmarks(frontImgRef.current, frontCanvasRef.current, landmarks))
  }

  // 드래그 중인 관절 하나의 좌표를 포인터 위치로 갱신한다. 리액트 state 갱신(비동기)을
  // 기다리면 드래그 중 화면이 한 프레임씩 밀려 보이므로, 캔버스는 즉시(동기) 다시 그리고
  // state는 그 다음 줄에서 갱신한다 — 두 갱신 모두 같은 updated 배열을 쓰므로 어긋나지 않는다.
  const updateLandmarkPosition = (which, index, clientX, clientY) => {
    const canvasEl = which === 'side' ? sideCanvasRef.current : frontCanvasRef.current
    const imgEl = which === 'side' ? sideImgRef.current : frontImgRef.current
    const landmarks = which === 'side' ? sideLandmarks : frontLandmarks
    if (!canvasEl || !landmarks) return
    const { x, y } = pixelToNormalized(canvasEl, clientX, clientY)
    const updated = withUpdatedLandmark(landmarks, index, x, y)
    drawLandmarks(imgEl, canvasEl, updated)
    if (which === 'side') {
      setSideLandmarks(updated)
    } else {
      setFrontLandmarks(updated)
    }
  }

  const handlePointerDown = (which) => (e) => {
    const landmarks = which === 'side' ? sideLandmarks : frontLandmarks
    const canvasEl = which === 'side' ? sideCanvasRef.current : frontCanvasRef.current
    if (!landmarks || !canvasEl) return
    const index = findNearestKeyLandmark(canvasEl, landmarks, e.clientX, e.clientY)
    if (index == null) return // 핵심 관절점 근처가 아니면 드래그 시작하지 않음(오클릭 방지)
    draggingRef.current = { which, index }
    canvasEl.setPointerCapture(e.pointerId) // 포인터가 캔버스 밖으로 나가도 드래그 계속 추적
    e.preventDefault()
  }

  const handlePointerMove = (which) => (e) => {
    const dragging = draggingRef.current
    if (!dragging || dragging.which !== which) return
    updateLandmarkPosition(which, dragging.index, e.clientX, e.clientY)
    e.preventDefault()
  }

  const handlePointerUp = (which) => (e) => {
    const dragging = draggingRef.current
    if (!dragging || dragging.which !== which) return
    draggingRef.current = null
    const canvasEl = which === 'side' ? sideCanvasRef.current : frontCanvasRef.current
    if (canvasEl && canvasEl.hasPointerCapture?.(e.pointerId)) {
      canvasEl.releasePointerCapture(e.pointerId)
    }
  }

  // MediaPipe가 처음 잡아준 위치로 되돌린다 — 드래그로 고친 게 오히려 더 이상해졌을 때의 안전망.
  const handleReset = (which) => () => {
    const original = which === 'side' ? sideOriginalLandmarks : frontOriginalLandmarks
    if (!original) return
    if (which === 'side') {
      setSideLandmarks(original)
      requestAnimationFrame(() => drawLandmarks(sideImgRef.current, sideCanvasRef.current, original))
    } else {
      setFrontLandmarks(original)
      requestAnimationFrame(() => drawLandmarks(frontImgRef.current, frontCanvasRef.current, original))
    }
  }

  // 측면(필수) 랜드마크로 계산한 값 + 정면(있으면) 랜드마크로 계산한 무릎모임/비대칭 값을
  // AngleFrame 3개(타임스탬프만 다름)로 복제해 /ai/coaching/frame(AI-06)에 보낸다 — 값이
  // 동일하니 서버가 "정지" 상태로 인식해 실제 임계값 비교가 적용된다(파일 상단 주석 참고).
  const requestJudgment = async () => {
    if (!sideLandmarks) return
    setJudging(true)
    setJudgeError('')
    setJudgeResult(null)
    const baseFrame = {
      knee_angle: getKneeAngle(sideLandmarks),
      hip_angle: getHipAngle(sideLandmarks),
      shoulder_forward_lean_deg: getShoulderForwardLeanDeg(sideLandmarks),
      heel_lift_ratio: getHeelLiftRatio(sideLandmarks),
      knee_over_toe_ratio: getKneeOverToeRatio(sideLandmarks),
    }
    if (frontLandmarks) {
      baseFrame.knee_valgus_ratio = getKneeValgusRatio(frontLandmarks)
      baseFrame.knee_asymmetry_deg = getKneeLrAsymmetryDeg(frontLandmarks)
    }
    const angle_history = [0, 0.1, 0.2].map((timestamp) => ({ timestamp, ...baseFrame }))
    try {
      const res = await fetch(`${AI_BASE}/ai/coaching/frame`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ angle_history }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setJudgeResult(await res.json())
    } catch (err) {
      setJudgeError(`AI 서버 연결 실패: ${err.message} (AI 서버가 localhost:8000에서 실행 중인지 확인해주세요)`)
    } finally {
      setJudging(false)
    }
  }

  return (
    <div className="app revealed">
      <main className="main">
        <div className="content">
          <div className="section-head">
            <div>
              <div className="section-eyebrow">POSE TEST</div>
              <div className="section-title">사진 측정 연습 페이지</div>
            </div>
          </div>

          <p className="pcard-desc" style={{ marginBottom: 12 }}>
            <span style={{ color: LEFT_COLOR }}>●</span> 왼쪽 관절&nbsp;&nbsp;
            <span style={{ color: RIGHT_COLOR }}>●</span> 오른쪽 관절&nbsp;&nbsp;
            (점 옆에 "?"가 붙으면 인식 신뢰도가 낮은 관절이에요 — 가려졌을 가능성)
            <br />
            각도/비율 계산은 프론트에서 하고, 정상/이상 판정은 아래 버튼으로 AI 서버(AI-06
            실시간 코칭)에 물어봐요. 정지 자세 1차 판정(AI-03)은 팀원 서비스가 담당해요.
            <br />
            관절 인식이 엉뚱한 위치를 잡으면(예: 가려진 부위) 그 점을 사진 위에서 마우스/터치로
            눌러 드래그하면 위치를 고칠 수 있어요 — 고친 위치가 아래 측정값/판정에 바로 반영돼요.
          </p>

          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
            <PhotoCard
              label="측면 사진"
              imageUrl={sideImageUrl}
              landmarks={sideLandmarks}
              onFile={handleFile('side')}
              onImageLoad={handleSideImageLoad}
              imgRef={sideImgRef}
              canvasRef={sideCanvasRef}
              notReadyMessage="무릎/엉덩이/어깨/발뒤꿈치/무릎-발끝 측정에 쓰여요."
              onPointerDown={handlePointerDown('side')}
              onPointerMove={handlePointerMove('side')}
              onPointerUp={handlePointerUp('side')}
              onReset={sideOriginalLandmarks ? handleReset('side') : null}
            />
            <PhotoCard
              label="정면 사진 (선택)"
              imageUrl={frontImageUrl}
              landmarks={frontLandmarks}
              onFile={handleFile('front')}
              onImageLoad={handleFrontImageLoad}
              imgRef={frontImgRef}
              canvasRef={frontCanvasRef}
              notReadyMessage="무릎 모임/좌우 비대칭/어깨·골반 좌우 기울기 측정에 쓰여요."
              onPointerDown={handlePointerDown('front')}
              onPointerMove={handlePointerMove('front')}
              onPointerUp={handlePointerUp('front')}
              onReset={frontOriginalLandmarks ? handleReset('front') : null}
            />
          </div>

          {loading && <p className="pcard-desc" style={{ marginTop: 12 }}>분석 중...</p>}
          {status && <p className="pcard-desc" style={{ marginTop: 12 }}>{status}</p>}

          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
            <MeasurementPanel title="측면 측정값" landmarks={sideLandmarks} />
            <FrontalMeasurementPanel landmarks={frontLandmarks} />
          </div>

          {sideLandmarks && (
            <button
              onClick={requestJudgment}
              disabled={judging}
              style={{ marginTop: 16 }}
            >
              {judging ? '판정 요청 중...' : 'AI 서버로 정상/이상 판정 요청'}
            </button>
          )}

          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
            <JudgmentPanel result={judgeResult} error={judgeError} loading={judging} />
          </div>
        </div>
      </main>
    </div>
  )
}

export default MlTestPage

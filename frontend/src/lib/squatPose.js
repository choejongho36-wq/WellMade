/**
 * 스쿼트 실시간 코칭(측면 카메라)에 필요한 관절 각도/비율 계산 + 스켈레톤 오버레이 그리기.
 *
 * 계산 공식은 예전 ai/app/pose/angles.py를 JS로 그대로 이식한 것이고(현재는 "무거운 연산은
 * 클라이언트, 서버는 경량 수치만 비교" 원칙에 따라 프론트가 담당), pages/MlTestPage.jsx의
 * 검증된 구현(실제 사진/영상으로 확인된 임계값·보정 포함)을 그대로 따른다 — 두 곳에서 같은
 * 공식이 따로 어긋나지 않도록, 새로 만드는 페이지(SquatCoachingPage)는 이 모듈을 공유해서
 * 쓴다.
 *
 * 정면 카메라 전용 값(무릎 모임 knee_valgus_ratio 등)은 넣지 않았다 — 실시간 코칭 페이지는
 * 측면 카메라 한 대로만 진행하는 흐름이라(캘리브레이션/모드 선택/정면 세트는 이번 스코프에
 * 포함하지 않음, 2026-09-02 대화 기준) 지금은 필요 없다.
 */

const LEFT_SHOULDER = 11
const RIGHT_SHOULDER = 12
const LEFT_HIP = 23
const RIGHT_HIP = 24
const LEFT_KNEE = 25
const RIGHT_KNEE = 26
const LEFT_ANKLE = 27
const RIGHT_ANKLE = 28
const LEFT_HEEL = 29
const RIGHT_HEEL = 30
const LEFT_FOOT_INDEX = 31
const RIGHT_FOOT_INDEX = 32
const LEFT_EAR = 7
const RIGHT_EAR = 8

// 발목-발끝 거리가 이보다 작으면(카메라를 거의 정면으로 보고 있거나 인식이 불안정) 방향
// 판단이 노이즈에 취약해져 계산을 포기하고 안전한 기본값을 반환한다.
const MIN_RELIABLE_FOOT_LENGTH = 0.03

// 허벅지(엉덩이-무릎) 길이가 이보다 작으면(카메라가 너무 멀거나 하체가 가려짐) 무릎-발끝
// 비율의 분모로 쓰기에 불안정해 계산을 포기한다.
// TODO: 팀 확정 필요 — 실측 데이터로 검증된 값이 아니라 발 길이 임곗값과 같은 자릿수(0.03)를
// 잠정 적용한 값이다 (ai/app 쪽 동일 TODO와 같은 배경).
const MIN_RELIABLE_THIGH_LENGTH = 0.03

export const KEY_LANDMARKS = {
  leftEar: LEFT_EAR,
  rightEar: RIGHT_EAR,
  leftShoulder: LEFT_SHOULDER,
  rightShoulder: RIGHT_SHOULDER,
  leftHip: LEFT_HIP,
  rightHip: RIGHT_HIP,
  leftKnee: LEFT_KNEE,
  rightKnee: RIGHT_KNEE,
  leftAnkle: LEFT_ANKLE,
  rightAnkle: RIGHT_ANKLE,
  leftHeel: LEFT_HEEL,
  rightHeel: RIGHT_HEEL,
  leftFootIndex: LEFT_FOOT_INDEX,
  rightFootIndex: RIGHT_FOOT_INDEX,
}

export const SKELETON_CONNECTIONS = [
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

export const LEFT_COLOR = '#00b894'
export const RIGHT_COLOR = '#e6432b'

// 코칭 판정에서 issue.part로 오는 영어 키를 화면에 보여줄 한국어 이름으로 바꾼다.
export const PART_LABELS = {
  knee: '무릎',
  hip: '엉덩이',
  shoulder: '어깨',
  heel: '발뒤꿈치',
  knee_valgus: '무릎 모임',
  knee_over_toe: '무릎-발끝',
  back_rounded: '등 굽음',
  center_of_mass: '무게중심',
  form_pattern: '전체 움직임 패턴',
  movement: '움직임',
  data: '데이터',
  gaze: '시선·목',
}

// ai/app/coaching/realtime.py의 STANDING_KNEE_ANGLE_MIN(150.0)과 동일한 기준 — 무릎 각도가
// 이 이상이면 서버가 "깊게 앉은 상태"로 보지 않아 깊이·엉덩이각·발뒤꿈치·무릎-발끝·무게중심
// 검사를 건너뛴다(목/시선 검사는 예외 — 앉은 정도와 무관하게 항상 확인한다). 프론트도 같은
// 기준으로 "판정 보류"를 표시하기 위해 값을 그대로 미러링해뒀다 — 서버 값이 바뀌면 같이 바꿔야 한다.
export const STANDING_KNEE_ANGLE_MIN = 150.0

// 사진 코칭 "분석 결과" 패널에 보여줄 지표 정의 — ai/app/pose/rules.py의 NORMAL_RANGES와
// 각 임곗값(threshold) 상수를 그대로 미러링한 표시용 설정이다.
//
// (2026-09-02 검수) 원래 디자인 시안에는 "무릎 각도 92°(권장 범위 85~100°)" · "등 기울기
// 38°" · "좌우 균형 96%" 같은 수치가 있었는데, claude/wellmade-squat-criteria-checklist.md와
// ai/app/pose/rules.py를 실제로 대조해보니 세 가지 다 실제 구현과 맞지 않았다:
// 1) 무릎 각도 정상 판정 구간은 85~100°가 아니라 30~120°다(NORMAL_RANGES["knee_angle"]) —
//    극단적인 이상만 걸러내도록 일부러 넓게 잡은 값이라, 85~100°처럼 좁은 "권장 범위"로
//    보여주면 실제 판정 기준을 오해하게 만든다.
// 2) "등 기울기"라는 단일 지표는 없다 — 목/시선(shoulder_forward_lean_deg, 40° 초과 시
//    이상) 지표와 등 굽음(torso_length_ratio, 온보딩 캘리브레이션 필요) 지표가 서로 다른
//    걸 재는데, 어느 쪽인지 알 수 없는 이름이었다. 아래 목록은 실제로 계산 가능한 "시선·목
//    기울기"만 넣었다.
// 3) "좌우 균형"(무릎 모임/좌우 비대칭)은 정면 카메라 랜드마크가 있어야 계산되는 값
//    (knee_valgus_ratio)인데, 사진 코칭은 측면 사진 한 장만 다루는 흐름이라 애초에 계산할
//    수 없다 — 아래 목록에서 뺐고, 대신 페이지 쪽에 "정면 촬영이 필요해요" 안내를 별도로 둔다.
//
// gated:true인 지표는 무릎이 충분히 굽혀졌을 때(knee_angle < STANDING_KNEE_ANGLE_MIN)만
// 서버가 실제로 판정한다 — 그 전에는 값 자체는 보여주되 배지는 "판정 보류"로 표시한다.
// ok는 "정상으로 보는 구간"이고, scale은 막대에서 보여줄 전체 범위(관측/이론상 값 폭에
// 여유를 둔 값 — 실측으로 확정된 경계는 아니다)다.
export const ANALYSIS_METRICS = [
  {
    part: 'knee',
    label: '무릎 각도',
    field: 'knee_angle',
    unit: '°',
    rangeText: '정상 판정 구간 30°~120° (깊게 앉았을 때 기준)',
    gated: true,
    scale: [0, 180],
    ok: [30, 120],
  },
  {
    part: 'hip',
    label: '엉덩이(고관절) 각도',
    field: 'hip_angle',
    unit: '°',
    rangeText: '정상 판정 구간 25°~120° (깊게 앉았을 때 기준)',
    gated: true,
    scale: [0, 180],
    ok: [25, 120],
  },
  {
    part: 'gaze',
    label: '시선 · 목 기울기',
    field: 'shoulder_forward_lean_deg',
    unit: '°',
    rangeText: '40° 이하면 정상 (앉은 정도와 무관하게 항상 확인)',
    gated: false,
    scale: [-40, 60],
    ok: [-40, 40],
  },
  {
    part: 'heel',
    label: '발뒤꿈치 들림',
    field: 'heel_lift_ratio',
    unit: '',
    rangeText: '0.7 이하면 정상 (깊게 앉았을 때 기준)',
    gated: true,
    scale: [-0.2, 1.4],
    ok: [-0.2, 0.7],
  },
  {
    part: 'knee_over_toe',
    label: '무릎 - 발끝 거리',
    field: 'knee_over_toe_ratio',
    unit: '',
    rangeText: '0.2 이하면 정상 (깊게 앉았을 때 기준)',
    gated: true,
    scale: [-0.4, 0.6],
    ok: [-0.4, 0.2],
  },
  {
    part: 'center_of_mass',
    label: '무게중심 정렬',
    field: 'torso_shin_lean_gap_deg',
    unit: '°',
    rangeText: '25° 이하면 정상 (깊게 앉았을 때 기준)',
    gated: true,
    scale: [-10, 50],
    ok: [-10, 25],
  },
]

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

// "귀-엉덩이가 일자로 뻗는지"를 부호 있는 각도로 잰 값. 0이면 완전한 일자, 양수면 목이
// 더 앞으로 꺾인(고개가 앞으로 떨어진) 상태, 음수면 더 세워진(뒤로 젖혀진) 상태.
function getShoulderForwardLeanDeg(landmarks, side = 'auto') {
  const chosen = selectSide(landmarks, side)
  const [earIdx, shoulderIdx, hipIdx, ankleIdx, toeIdx] =
    chosen === 'left'
      ? [LEFT_EAR, LEFT_SHOULDER, LEFT_HIP, LEFT_ANKLE, LEFT_FOOT_INDEX]
      : [RIGHT_EAR, RIGHT_SHOULDER, RIGHT_HIP, RIGHT_ANKLE, RIGHT_FOOT_INDEX]
  const ear = landmarks[earIdx]
  const shoulder = landmarks[shoulderIdx]
  const hip = landmarks[hipIdx]
  const ankle = landmarks[ankleIdx]
  const toe = landmarks[toeIdx]
  const footLength = Math.abs(ankle.x - toe.x)
  if (footLength < MIN_RELIABLE_FOOT_LENGTH) return 0
  const facingDirection = toe.x - ankle.x >= 0 ? 1 : -1

  const torsoVec = { x: shoulder.x - hip.x, y: shoulder.y - hip.y }
  const neckVec = { x: ear.x - shoulder.x, y: ear.y - shoulder.y }
  const cross = torsoVec.x * neckVec.y - torsoVec.y * neckVec.x
  const dot = torsoVec.x * neckVec.x + torsoVec.y * neckVec.y
  return ((Math.atan2(cross, dot) * 180) / Math.PI) * facingDirection
}

// 발뒤꿈치-발끝 높이차 / 발 길이. 값이 클수록 발뒤꿈치가 뜬 상태.
function getHeelLiftRatio(landmarks, side = 'auto') {
  const chosen = selectSide(landmarks, side)
  const [heelIdx, toeIdx, ankleIdx] = chosen === 'left' ? [LEFT_HEEL, LEFT_FOOT_INDEX, LEFT_ANKLE] : [RIGHT_HEEL, RIGHT_FOOT_INDEX, RIGHT_ANKLE]
  const heel = landmarks[heelIdx]
  const toe = landmarks[toeIdx]
  const ankle = landmarks[ankleIdx]
  const footLength = Math.abs(ankle.x - toe.x)
  if (footLength < MIN_RELIABLE_FOOT_LENGTH) return 0
  return (toe.y - heel.y) / footLength
}

// 무릎-발끝 거리 / 허벅지(엉덩이-무릎) 길이. 값이 0 이하면 무릎이 발끝을 안 넘은 상태.
function getKneeOverToeRatio(landmarks, side = 'auto') {
  const chosen = selectSide(landmarks, side)
  const [kneeIdx, hipIdx, ankleIdx, toeIdx] =
    chosen === 'left' ? [LEFT_KNEE, LEFT_HIP, LEFT_ANKLE, LEFT_FOOT_INDEX] : [RIGHT_KNEE, RIGHT_HIP, RIGHT_ANKLE, RIGHT_FOOT_INDEX]
  const knee = landmarks[kneeIdx]
  const hip = landmarks[hipIdx]
  const ankle = landmarks[ankleIdx]
  const toe = landmarks[toeIdx]
  const footLength = Math.abs(ankle.x - toe.x)
  if (footLength < MIN_RELIABLE_FOOT_LENGTH) return null
  const thighLength = Math.hypot(hip.x - knee.x, hip.y - knee.y)
  if (thighLength < MIN_RELIABLE_THIGH_LENGTH) return null
  const facingDirection = toe.x - ankle.x >= 0 ? 1 : -1
  return ((knee.x - toe.x) * facingDirection) / thighLength
}

// 상체(어깨-엉덩이)와 정강이(무릎-발목)가 각각 수직선 대비 얼마나 앞으로 기울었는지의 차이.
// 무게중심이 지지기반(발) 뒤쪽에 남는 자세를 잡기 위한 신호.
function getTorsoShinLeanGapDeg(landmarks, side = 'auto') {
  const chosen = selectSide(landmarks, side)
  const [shoulderIdx, hipIdx, kneeIdx, ankleIdx, toeIdx] =
    chosen === 'left'
      ? [LEFT_SHOULDER, LEFT_HIP, LEFT_KNEE, LEFT_ANKLE, LEFT_FOOT_INDEX]
      : [RIGHT_SHOULDER, RIGHT_HIP, RIGHT_KNEE, RIGHT_ANKLE, RIGHT_FOOT_INDEX]
  const shoulder = landmarks[shoulderIdx]
  const hip = landmarks[hipIdx]
  const knee = landmarks[kneeIdx]
  const ankle = landmarks[ankleIdx]
  const toe = landmarks[toeIdx]
  const footLength = Math.abs(ankle.x - toe.x)
  if (footLength < MIN_RELIABLE_FOOT_LENGTH) return 0
  const facingDirection = toe.x - ankle.x >= 0 ? 1 : -1

  const torsoDx = (shoulder.x - hip.x) * facingDirection
  const torsoDy = -(shoulder.y - hip.y)
  const torsoLeanDeg = (Math.atan2(torsoDx, torsoDy) * 180) / Math.PI

  const shinDx = (knee.x - ankle.x) * facingDirection
  const shinDy = -(knee.y - ankle.y)
  const shinLeanDeg = (Math.atan2(shinDx, shinDy) * 180) / Math.PI

  return torsoLeanDeg - shinLeanDeg
}

// 측면 랜드마크 1세트에서 AI-06(/ai/coaching/frame)의 AngleFrame에 필요한 필드를 뽑아낸다.
export function buildSideMetrics(landmarks) {
  return {
    knee_angle: getKneeAngle(landmarks),
    hip_angle: getHipAngle(landmarks),
    shoulder_forward_lean_deg: getShoulderForwardLeanDeg(landmarks),
    heel_lift_ratio: getHeelLiftRatio(landmarks),
    knee_over_toe_ratio: getKneeOverToeRatio(landmarks),
    torso_shin_lean_gap_deg: getTorsoShinLeanGapDeg(landmarks),
  }
}

// 33개 랜드마크 중 핵심 관절만 웹캠 화면 위에 스켈레톤으로 그린다(디버그용 라벨 없이,
// 실제 사용자 화면에 보여줄 수 있는 깔끔한 버전 — MlTestPage.jsx의 drawLandmarks와 달리
// 이름표/시각화 좌표를 찍지 않는다).
export function drawSkeleton(videoEl, canvasEl, landmarks) {
  if (!videoEl || !canvasEl || !landmarks) return
  const width = videoEl.clientWidth
  const height = videoEl.clientHeight
  if (!width || !height) return
  if (canvasEl.width !== width) canvasEl.width = width
  if (canvasEl.height !== height) canvasEl.height = height
  const ctx = canvasEl.getContext('2d')
  ctx.clearRect(0, 0, width, height)

  ctx.lineWidth = 3
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

  Object.entries(KEY_LANDMARKS).forEach(([name, idx]) => {
    const lm = landmarks[idx]
    if (!lm) return
    const visibility = lm.visibility ?? 1
    ctx.globalAlpha = Math.max(visibility, 0.3)
    ctx.beginPath()
    ctx.arc(lm.x * width, lm.y * height, 5, 0, Math.PI * 2)
    ctx.fillStyle = name.startsWith('left') ? LEFT_COLOR : RIGHT_COLOR
    ctx.fill()
    ctx.globalAlpha = 1
  })
}


// 이미 촬영해서 정지된 사진(캔버스) 위에 스켈레톤을 그려 넣는다. drawSkeleton은 실시간
// <video> 엘리먼트의 clientWidth/clientHeight를 기준으로 그리지만, 사진 코칭은 캡처된
// 정지 이미지(오프스크린 캔버스) 위에 그려야 해서 별도로 뒀다 — 소스 캔버스 해상도
// 그대로 새 캔버스에 사진+스켈레톤을 합성해 반환한다(화면에는 CSS로 축소해서 보여준다).
export function renderPhotoWithSkeleton(sourceCanvas, landmarks) {
  const width = sourceCanvas.width
  const height = sourceCanvas.height
  const out = document.createElement('canvas')
  out.width = width
  out.height = height
  const ctx = out.getContext('2d')
  ctx.drawImage(sourceCanvas, 0, 0)

  if (landmarks) {
    ctx.lineWidth = 3
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
    Object.entries(KEY_LANDMARKS).forEach(([name, idx]) => {
      const lm = landmarks[idx]
      if (!lm) return
      const visibility = lm.visibility ?? 1
      ctx.globalAlpha = Math.max(visibility, 0.3)
      ctx.beginPath()
      ctx.arc(lm.x * width, lm.y * height, 6, 0, Math.PI * 2)
      ctx.fillStyle = name.startsWith('left') ? LEFT_COLOR : RIGHT_COLOR
      ctx.fill()
      ctx.globalAlpha = 1
    })
  }

  return out
}

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

// 어깨 사이 가로 거리가 이보다 좁으면(정면이 아니라 측면에 가까운 각도로 찍힌 사진) "정면
// 사진"으로 보지 않고 무릎모임(valgus) 판정을 건너뛴다 — 측면 사진에서는 카메라 각도상
// 양 어깨가 거의 겹쳐 보여 이 거리가 아주 작게 나온다(2026-09-02, 측면 사진을 정면 칸에
// 올렸을 때 무릎모임이 잘못 표시되던 문제 수정 — 사용자 피드백 반영).
const MIN_FRONTAL_SHOULDER_WIDTH = 0.1

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

// 사진 코칭 "정면/측면 사진 미리보기"의 드래그 가능한 좌표 점 색상(2026-09-02) — 실시간
// 코칭(LEFT_COLOR/RIGHT_COLOR, 웹캠 스켈레톤)과는 별도 용도라 색을 공유하지 않는다.
// 사용자가 이전에 받아본 관절 좌표 시각화 사진과 동일하게 분홍/파랑으로 맞췄다.
export const PHOTO_DOT_LEFT_COLOR = '#ec1e7a'
export const PHOTO_DOT_RIGHT_COLOR = '#2678eb'

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

// ai/app/pose/rules.py의 KNEE_VALGUS_RATIO_THRESHOLD(0.8)와 동일한 기준 — 무릎 사이
// 너비/발목 사이 너비 비율이 이보다 작으면 무릎 모임(valgus)으로 본다. 정면 사진만
// 올라와 AI-06(judge_realtime_coaching)을 호출하지 않는 경우, 프론트가 직접 이 기준으로
// 판정한다(getKneeValgusRatio/buildFrontMetrics 참고) — 서버 값이 바뀌면 같이 바꿔야 한다.
export const KNEE_VALGUS_RATIO_THRESHOLD = 0.8

// ai/app/pose/coaching_messages.py의 KNEE_VALGUS_MESSAGE와 동일한 문구 — 정면 사진
// 단독(측면 없음) 판정일 때 프론트가 서버를 거치지 않고 직접 issue를 만들 때 쓴다.
export const KNEE_VALGUS_MESSAGE = '무릎이 안쪽으로 모이고 있어요. 무릎이 발끝과 같은 방향을 향하도록 밀어주세요.'

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

// 무릎 사이 너비 / 발목 사이 너비. ai/app/pose/angles.py의 get_knee_valgus_ratio와 동일한
// 정의 — 정면(전신이 카메라를 보는) 랜드마크가 있어야 의미 있는 값이다. 값이
// KNEE_VALGUS_RATIO_THRESHOLD보다 작으면 무릎이 안쪽으로 모인 것으로 본다.
//
// (2026-09-02) 어깨 사이 거리로 "정면 사진이 맞는지" 먼저 확인한다 — 측면(옆모습)
// 사진에서는 카메라 각도상 무릎/발목도 거의 겹쳐 보여 비율이 구조적으로 낮게 나오기 때문에,
// 검증 없이 그대로 계산하면 측면 사진에서도 거의 항상 "무릎모임"으로 오탐된다. 정면 사진이
// 아니라고 판단되면(어깨 폭이 너무 좁으면) null을 돌려줘 판정 자체를 건너뛴다.
function getKneeValgusRatio(landmarks) {
  const shoulderWidth = Math.abs(landmarks[LEFT_SHOULDER].x - landmarks[RIGHT_SHOULDER].x)
  if (shoulderWidth < MIN_FRONTAL_SHOULDER_WIDTH) return null
  const kneeWidth = Math.abs(landmarks[LEFT_KNEE].x - landmarks[RIGHT_KNEE].x)
  const ankleWidth = Math.abs(landmarks[LEFT_ANKLE].x - landmarks[RIGHT_ANKLE].x)
  if (ankleWidth < MIN_RELIABLE_FOOT_LENGTH) return null
  return kneeWidth / ankleWidth
}

// 정면 랜드마크 1세트에서 뽑아낼 수 있는 필드(2026-09-02, 정면 사진 업로드 추가) —
// knee_valgus_ratio는 AI-06의 AngleFrame에도 그대로 실어 보낼 수 있는 선택 필드다
// (측면 사진이 함께 있을 때). 측면 사진이 없으면 이 값만으로 프론트가 직접 판정한다.
// 값이 null이면(정면 사진처럼 보이지 않을 때 포함) 무릎모임 판정 자체를 하지 않는다.
export function buildFrontMetrics(landmarks) {
  return {
    knee_valgus_ratio: getKneeValgusRatio(landmarks),
  }
}

// MediaPipe 원본 랜드마크 배열(33개, 인덱스 기반) → 화면에서 드래그로 옮길 수 있는
// "이름 기반" 좌표 객체로 변환한다(KEY_LANDMARKS의 14개 관절만). 사진 코칭의 드래그 가능한
// 좌표 편집기(PhotoLandmarkEditor)가 렌더링/드래그에 이 형태를 쓴다.
export function landmarksToEditablePoints(landmarks) {
  const points = {}
  for (const [name, idx] of Object.entries(KEY_LANDMARKS)) {
    const lm = landmarks[idx]
    if (!lm) continue
    points[name] = { x: lm.x, y: lm.y, visibility: lm.visibility ?? 1 }
  }
  return points
}

// landmarksToEditablePoints의 역변환 — 사용자가 드래그로 수정했을 수 있는 좌표 객체를
// buildSideMetrics/buildFrontMetrics가 기대하는 인덱스 기반 형태로 되돌린다(재분석 시 사용).
export function editablePointsToLandmarksArray(points) {
  const landmarks = {}
  for (const [name, idx] of Object.entries(KEY_LANDMARKS)) {
    if (points[name]) landmarks[idx] = points[name]
  }
  return landmarks
}

// 사진 미리보기 박스를 3:4(세로)로 고정할 때 쓰는 비율(2026-09-02, "사진 크기를 어떤
// 사진을 넣든 일정하게, 잘리지 않고 여백이 보이도록" 요청 반영) — object-fit: contain과
// 동일하게 사진 전체를 박스 안에 그대로 보여주고 남는 공간은 여백으로 둔다.
export const PHOTO_BOX_ASPECT_RATIO = 3 / 4 // 가로 / 세로

// 원본 사진 기준 정규화 좌표(0~1) → 3:4 박스 기준 정규화 좌표(0~1)로 변환한다.
// imageAspect(사진의 가로/세로 비율)에 따라 박스 안에서 사진이 위아래 또는 좌우 중 어느
// 쪽에 여백이 생기는지가 달라지므로 사진마다 다시 계산해야 한다 — object-fit: contain을
// CSS가 아니라 직접 계산하는 이유는, 그 위에 겹치는 좌표 점/스켈레톤 선(PhotoLandmarkEditor의
// SVG)도 같은 여백만큼 보정해야 정확한 관절 위치에 찍히기 때문이다. imageAspect를 아직
// 모르면(로딩 중 등) 보정 없이 그대로 반환한다.
export function imageToBoxPoint(nx, ny, imageAspect, boxAspect = PHOTO_BOX_ASPECT_RATIO) {
  if (!imageAspect) return { x: nx, y: ny }
  const scale = Math.min(boxAspect / imageAspect, 1)
  const displayedW = imageAspect * scale
  const displayedH = scale
  const offsetX = (boxAspect - displayedW) / 2
  const offsetY = (1 - displayedH) / 2
  return {
    x: (offsetX + nx * displayedW) / boxAspect,
    y: offsetY + ny * displayedH,
  }
}

// imageToBoxPoint의 역변환 — 드래그 중인 포인터가 박스 안 어디를 가리키는지(0~1, 박스
// 기준)를 원본 사진 기준 좌표로 되돌린다. 사진 바깥 여백(레터박스) 위를 드래그하면 사진
// 가장자리로 스냅되도록 0~1 범위로 잘라낸다(clamp).
export function boxToImagePoint(bx, by, imageAspect, boxAspect = PHOTO_BOX_ASPECT_RATIO) {
  if (!imageAspect) return { x: bx, y: by }
  const scale = Math.min(boxAspect / imageAspect, 1)
  const displayedW = imageAspect * scale
  const displayedH = scale
  const offsetX = (boxAspect - displayedW) / 2
  const offsetY = (1 - displayedH) / 2
  const nx = (bx * boxAspect - offsetX) / displayedW
  const ny = (by - offsetY) / displayedH
  return {
    x: Math.max(0, Math.min(1, nx)),
    y: Math.max(0, Math.min(1, ny)),
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

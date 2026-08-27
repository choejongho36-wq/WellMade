import { useEffect, useRef, useState } from 'react'
import './MlTestPage.css'
import PageShell from '../components/PageShell.jsx'
import { usePoseLandmarker } from '../hooks/usePoseLandmarker.js'

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

// 허벅지(엉덩이-무릎) 길이가 이보다 작으면(카메라가 너무 멀거나 하체가 가려짐)
// 무릎-발끝 비율의 분모로 쓰기에 불안정해 계산을 포기한다. 발 길이 임곗값과 달리
// 아직 실측 데이터로 검증한 값이 아니라, 우선 같은 자릿수(0.03)를 잠정 적용했다.
// TODO: 팀 확정 필요 — 실측 데이터(build_dtw_templates.py 재추출)로 검증.
const MIN_RELIABLE_THIGH_LENGTH = 0.03

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

// "귀-엉덩이가 일자로 뻗는지"를 각도로 잰 값 — 엉덩이→어깨 방향(상체)을 그대로
// 연장했을 때의 방향과, 실제 어깨→귀 방향(목) 사이의 각도 차이다. 0이면 완전한 일자,
// 양수면 그 연장선보다 목이 더 앞으로 꺾인(고개가 앞으로 떨어진) 상태, 음수면 그
// 연장선보다 목이 더 세워진(뒤로 젖혀진) 상태 — 음수는 현재 정상으로 취급한다.
// (2026-08-27 변경) 원래는 목 기울기·상체 기울기를 각각 atan2로 따로 구해서 뺐는데,
// 이건 "귀-어깨-엉덩이가 일자인지"와 수학적으로 동일한 값이다 — getShoulderAlignmentAngle()
// (귀-어깨-엉덩이 3점 각도)의 180도 보각과 정확히 일치함을 실제 사진 데이터로 확인했다
// (36.9도로 일치). 다만 getShoulderAlignmentAngle()은 acos 기반이라 부호가 없어(0~180도)
// 앞으로 숙임과 뒤로 젖힘을 구분 못 해 그대로 가져다 쓸 수는 없었고, 대신 상체 벡터와
// 목 벡터 사이의 부호 있는 각도를 외적·내적으로 한 번에 구하는 방식으로 단순화했다 —
// atan2 두 번 + 뺄셈이 atan2 한 번으로 줄었다(좌우 반전 케이스까지 부호 대칭 검증 완료,
// 결과값은 기존 방식과 동일).
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

  const torsoVec = { x: shoulder.x - hip.x, y: shoulder.y - hip.y }
  const neckVec = { x: ear.x - shoulder.x, y: ear.y - shoulder.y }
  const cross = torsoVec.x * neckVec.y - torsoVec.y * neckVec.x
  const dot = torsoVec.x * neckVec.x + torsoVec.y * neckVec.y
  return ((Math.atan2(cross, dot) * 180) / Math.PI) * facingDirection
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

// 무릎-발끝 거리 / 허벅지(엉덩이-무릎) 길이. 값이 0 이하면 무릎이 발끝을 안 넘은 상태,
// 클수록 허벅지 길이 대비 많이 넘은 상태.
// (2026-08-27 변경) 예전에는 발 길이로 정규화하지 않고 원시 좌표 거리만 썼는데, 스쿼트
// 스탠스 때문에 발이 자연스럽게 바깥으로 돌아가면(외회전) 발 길이 자체가 코사인 배율로
// 줄어들어 자로 쓰기 불안정했다 — 실제로 정상적인 딥스쿼트 사진에서 오탐이 확인됐다
// (checklist 2026-08-27 addendum 참고). 허벅지는 스쿼트의 주된 움직임(고관절·무릎 굽힘)이
// 카메라 화면과 평행한 면 안에서 일어나는 회전이라 자세가 바뀌어도 화면상 길이가 거의
// 안 변하고, 뼈 구간이라 등 굽음 같은 척추 변형에도 흔들리지 않아 발보다 안정적인 자다.
// facingDirection(몸이 향한 방향 보정)은 여전히 발목-발끝 오프셋으로 판단하므로, 그 판단이
// 신뢰할 수 없는 경우(발이 카메라를 거의 정면으로 향함)에는 별도 게이트를 그대로 둔다.
// 두 게이트(발 길이/허벅지 길이) 중 하나라도 걸리면 null을 반환한다 — 예전에는 0을
// 반환했는데, 0은 "무릎이 발끝을 안 넘은 안전한 상태"를 뜻하는 값이라 "측정 불가"와
// 구분이 안 됐다(getTorsoLengthRatio와 동일하게 null로 통일).
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

// 상체(어깨-엉덩이)와 정강이(무릎-발목)가 각각 수직선 대비 얼마나 앞으로 기울었는지를 구해서
// 그 차이를 본다. 정강이는 거의 안 기울었는데(발목 가동범위가 부족해 무릎이 발끝 쪽으로
// 못 나감) 상체만 훨씬 더 기울어 있다면, 발목 대신 상체가 그 부족분을 보상하고 있다는
// 뜻이고, 무게중심이 지지기반(발) 뒤쪽에 가깝게 남는다 — "앞에 반대 방향 무게(바/플레이트)가
// 없으면 뒤로 넘어갈 것 같다"는 인상으로 이어지는 자세다.
// (2026-08-27 추가) 팀에서 "무게중심이 무너진 것 같다"고 지적한 실제 사진 2장(다른 사람·
// 다른 기구·다른 출처, checklist 2026-08-27 addendum 8번 참고)에서 이 값이 각각 27.2도·
// 28.9도로 나왔고, 확인된 정상 사진 10장은 전부 -2.0~23.3도 사이였다. 상체·정강이 각각의
// 절대 기울기는 체형(다리 길이 등)에 따라 편차가 컸지만(정상 사진만 봐도 상체 기울기가
// 15.6~48.9도로 넓게 퍼짐 — 절대각도 단독으로는 정상/이상이 안 갈렸다), 두 값의 "차이"는
// 체형과 무관하게 정상군과 나쁜 사례가 갈리는 것을 확인했다.
// 먼저 시도했던 "엉덩이가 지지기반(발뒤꿈치)보다 얼마나 뒤로 벗어났는지"(발 길이/허벅지
// 길이로 각각 정규화) 지표는 실측에서 정상 사진들과 구분이 안 됐고(정상 사진 안에서도
// 편차가 너무 컸음), 예전에 비슷한 접근(어깨-무릎 직선 기준 엉덩이 이탈)을 실제 적용했을 때
// 모든 사진에서 이상이 뜨는 문제로 폐기했던 것과 같은 실패 패턴이라 이번엔 채택하지 않았다.
// TODO: 팀 확정 필요(중요) — 나쁜 사례가 아직 2건뿐이라 임계값(rules.py의
// TORSO_SHIN_LEAN_GAP_THRESHOLD_DEG) 검증 표본이 매우 작다. 실사용자 테스트로 반드시
// 재검증할 것.
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

// 측면 랜드마크 1세트에서 AI-06(/ai/coaching/frame)의 AngleFrame에 필요한 필드만 뽑아낸다.
// 사진 판정(requestJudgment)과 영상 판정(아래 handleVideoLoadedMetadata) 양쪽에서 같은
// 함수를 공유해서 쓴다 — 계산 공식이 두 곳에서 따로 어긋나는 걸 막기 위함.
function buildSideMetrics(landmarks) {
  return {
    knee_angle: getKneeAngle(landmarks),
    hip_angle: getHipAngle(landmarks),
    shoulder_forward_lean_deg: getShoulderForwardLeanDeg(landmarks),
    heel_lift_ratio: getHeelLiftRatio(landmarks),
    knee_over_toe_ratio: getKneeOverToeRatio(landmarks),
    torso_shin_lean_gap_deg: getTorsoShinLeanGapDeg(landmarks),
  }
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
  return value == null ? '측정 불가 (기준 길이 너무 짧음)' : value.toFixed(digits)
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
        <div>무릎-발끝/허벅지 길이 비율: {fmt(getKneeOverToeRatio(landmarks), 3)}</div>
        <div>어깨-엉덩이/발 길이 비율: {fmt(getTorsoLengthRatio(landmarks), 3)}</div>
        <div>상체-정강이 기울기 차이(무게중심): {fmt(getTorsoShinLeanGapDeg(landmarks))}도</div>
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

// (2026-08-27) hip_hyperextension 라벨은 그 판정 로직 자체가 근거 부족으로 폐기되며
// 함께 제거했다(rules.py의 HIP_HYPEREXTENSION_VALGUS_THRESHOLD 자리 주석 참고).
// center_of_mass는 그 판정 로직을 추가할 때 이 라벨 매핑에 넣는 걸 빠뜨렸던 걸 이번에 보강.
const PART_LABELS = {
  knee: '무릎',
  hip: '엉덩이',
  shoulder: '어깨',
  heel: '발뒤꿈치',
  knee_valgus: '무릎 모임',
  asymmetry: '좌우 비대칭',
  knee_over_toe: '무릎-발끝',
  back_rounded: '등 굽음',
  center_of_mass: '무게중심',
  form_pattern: '전체 움직임 패턴',
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

// 자동 감지된 렙(스쿼트 저점) 하나의 판독 결과를 보여준다. 클릭하면 그 프레임으로 이동한다
// (videoSliderIndex를 공유하는 또 다른 입력 수단 — 그래프/슬라이더와 동일한 패턴).
function RepResultCard({ rep, repIndex, active, onClick }) {
  const { timestamp, kneeAngle, result, error, loading } = rep
  return (
    <div
      className="pcard"
      onClick={onClick}
      style={{
        maxWidth: 220,
        flex: '1 1 200px',
        cursor: 'pointer',
        outline: active ? `2px solid ${LEFT_COLOR}` : 'none',
      }}
    >
      <div className="pcard-body" style={{ fontSize: 13, lineHeight: 1.6 }}>
        <div className="pcard-title">
          렙 {repIndex + 1} · {timestamp.toFixed(2)}초
        </div>
        <div>무릎각도 {kneeAngle.toFixed(1)}도</div>
        {loading && <div style={{ marginTop: 4 }}>AI 판독 중...</div>}
        {error && (
          <div style={{ marginTop: 4, color: '#e6432b' }}>
            {error}
          </div>
        )}
        {result && (
          <div style={{ marginTop: 4 }}>
            <span style={{ color: result.is_normal ? '#2eb872' : '#e6432b', fontWeight: 600 }}>
              {result.is_normal ? '정상' : '이상'}
            </span>{' '}
            · 동작 단계: {result.phase} · 신뢰도 {(result.confidence * 100).toFixed(0)}%
            {result.issues.length > 0 && (
              <div style={{ marginTop: 4 }}>
                {result.issues.map((issue, i) => (
                  <div key={i}>
                    · [{PART_LABELS[issue.part] ?? issue.part}] {issue.message}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ---- 영상 모드 ----
// (2026-08-25 추가) 사진 모드는 "값이 동일한 프레임 3개"를 만들어 서버가 항상 정지(holding)
// 상태로 인식하게 우회하는데, 이러면 AI-06이 원래 설계된 목적(실제 시간 흐름에 따른
// 내려감/올라옴/정지 판정)을 테스트해볼 수가 없다. 영상 모드는 실제 타임스탬프가 있는
// 프레임 시계열을 그대로 만들어 보내서, 이 판정 로직 자체가 실제 동작에 얼마나 잘 맞는지
// (특히 최근 논의한 "자연스럽게 앉았다 일어나기 vs 몇 초 유지하기" 질문)를 검증하기 위한
// 용도다.
const VIDEO_SAMPLE_INTERVAL_SEC = 0.15 // 기본 샘플링 간격(초) — 대략 6~7fps
const VIDEO_MAX_FRAMES = 60 // 긴 영상을 올려도 이 개수를 넘지 않도록 간격을 늘려서 맞춘다
const VIDEO_MIN_USABLE_FRAMES = 3 // 서버(judge_realtime_coaching)의 MIN_FRAMES와 동일한 기준
// 영상 전체를 한 번에 서버로 보내면 "내려갔다 올라오는 전체 구간"의 기울기가 서로
// 상쇄되어 판정이 무의미해진다. 실제 서비스가 매 호출마다 "최근 N프레임"만 보내는 것과
// 같은 형태(롤링 윈도우)로 재현해야, 슬라이더로 고른 시점의 국소적인 변화 방향(내려가는
// 중/올라오는 중/정지)이 그 순간 기준으로 제대로 판정된다.
const VIDEO_JUDGE_WINDOW = 6

// (2026-08-25 추가) "가장 무릎각도가 작을 때 = 스쿼트 저점"을 사람이 슬라이더로 찾지 않고
// AI가 직접 찾아서 그 순간을 판독하게 해달라는 요청에 따라 추가한 자동 렙(rep) 감지 기준.
// STANDING_KNEE_ANGLE_MIN은 서버(ai/app/coaching/realtime.py)의 같은 이름 상수와 값을
// 맞췄다 — 이 값보다 무릎각도가 작아야만 "실제로 앉은 상태"로 보고, 서 있는 채로 무릎이
// 살짝 흔들리는 것까지 저점으로 잡지 않는다.
const STANDING_KNEE_ANGLE_MIN = 150
// 한 번 저점을 인정한 뒤, 이 프레임 수 안에서 나오는 다른 국소최소값은 같은 렙의 노이즈로
// 보고 새 렙으로 세지 않는다(단, 그 안에서 더 낮은 지점이 나오면 그쪽으로 갱신한다).
// TODO: 팀 확정 필요 — 실제 사용자 템포(렙 사이 간격)로 튜닝이 필요한 값의 초안이다.
const REP_BOTTOM_MIN_GAP_FRAMES = 8

// 무릎각도 시계열에서 "저점(가장 깊이 앉은 순간)"들을 자동으로 찾는다. 이웃 프레임보다
// 낮거나 같은 국소최소값을 후보로 두고, 위 두 기준(STANDING_KNEE_ANGLE_MIN, MIN_GAP)으로
// 노이즈를 거른다. 반환값은 videoFrames 배열의 인덱스 목록(오름차순, 렙 등장 순서).
function detectRepBottoms(frames) {
  const bottoms = []
  for (let i = 0; i < frames.length; i++) {
    const angle = frames[i].metrics.knee_angle
    if (angle >= STANDING_KNEE_ANGLE_MIN) continue
    const prev = frames[i - 1]?.metrics.knee_angle
    const next = frames[i + 1]?.metrics.knee_angle
    const isLocalMin = (prev === undefined || angle <= prev) && (next === undefined || angle <= next)
    if (!isLocalMin) continue

    const lastIdx = bottoms.length - 1
    if (lastIdx >= 0 && i - bottoms[lastIdx] < REP_BOTTOM_MIN_GAP_FRAMES) {
      if (angle < frames[bottoms[lastIdx]].metrics.knee_angle) bottoms[lastIdx] = i
      continue
    }
    bottoms.push(i)
  }
  return bottoms
}

// ---- 실시간 영상(웹캠) 모드 ----
// (2026-08-25 추가) "나중에 진짜로 영상을 찍어보기 전에 실시간 모드도 미리 확인해보고
// 싶다"는 요청으로 추가했다. 파일 업로드 영상 모드와 달리 끝이 없는 스트림이라 프레임을
// 전부 모아두지 않고, 최근 LIVE_BUFFER_MAX개만 롤링 버퍼로 들고 있다가 새 프레임이 들어올
// 때마다 그 순간까지의 최근 윈도우(judgeWindow — 영상 모드와 동일 함수 재사용)를 AI-06에
// 보낸다. 이게 바로 실제 서비스가 웹캠으로 하려는 것과 동일한 흐름이다.
const LIVE_SAMPLE_INTERVAL_MS = 200 // 실시간 판독 주기(ms) — 영상 모드 샘플링(~0.15초)과 비슷한 수준
const LIVE_BUFFER_MAX = 30 // 이 개수를 넘는 오래된 프레임은 버린다(약 6초 분량)

// <video>의 currentTime을 원하는 시점으로 옮기고, 실제로 그 프레임까지 디코딩이 끝나는
// 'seeked' 이벤트를 기다린다. 일부 브라우저/코덱 조합에서는 이미 같은 시점에 있을 때
// (특히 0초) 'seeked'가 아예 안 오는 경우가 있어, 무한 대기를 막는 타임아웃 안전장치를 둔다.
function seekVideo(video, t) {
  return new Promise((resolve) => {
    let done = false
    const finish = () => {
      if (done) return
      done = true
      video.removeEventListener('seeked', finish)
      resolve()
    }
    video.addEventListener('seeked', finish)
    video.currentTime = t
    setTimeout(finish, 1500)
  })
}

const REP_MARKER_COLOR = '#ffb020'

// 무릎각도 시계열을 아주 단순한 꺾은선 그래프로 보여준다. 프레임마다 다시 관절 인식을
// 돌리지 않고(추출 단계에서 이미 계산해둔 값을 재사용), 클릭한 지점의 프레임으로 바로
// 이동할 수 있게 슬라이더와 같은 상태(videoSliderIndex)를 공유한다. repMarkers는
// detectRepBottoms가 자동으로 찾아낸 저점들을 주황 점으로 표시한다.
function KneeAngleSparkline({ frames, currentIndex, repMarkers = [], onSelect = () => {} }) {
  if (frames.length < 2) return null
  const width = 480
  const height = 72
  const padding = 6
  const angles = frames.map((f) => f.metrics.knee_angle)
  const min = Math.min(...angles)
  const max = Math.max(...angles)
  const range = max - min || 1
  const xStep = (width - padding * 2) / (frames.length - 1)
  const toXY = (i) => [padding + i * xStep, padding + (1 - (angles[i] - min) / range) * (height - padding * 2)]
  const points = frames.map((_, i) => toXY(i).join(',')).join(' ')
  const [curX, curY] = toXY(currentIndex)

  const handleClick = (e) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const relX = ((e.clientX - rect.left) / rect.width) * width
    const idx = Math.round((relX - padding) / xStep)
    onSelect(Math.max(0, Math.min(frames.length - 1, idx)))
  }

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      style={{ width: '100%', maxWidth: width, cursor: 'pointer', marginTop: 8 }}
      onClick={handleClick}
    >
      <polyline points={points} fill="none" stroke={LEFT_COLOR} strokeWidth="1.5" opacity="0.8" />
      {repMarkers.map((idx) => {
        const [mx, my] = toXY(idx)
        return <circle key={idx} cx={mx} cy={my} r="4" fill={REP_MARKER_COLOR} stroke="#000" strokeWidth="1" />
      })}
      <line x1={curX} y1={padding} x2={curX} y2={height - padding} stroke="#fff" strokeWidth="1" opacity="0.5" />
      <circle cx={curX} cy={curY} r="3.5" fill={LEFT_COLOR} stroke="#000" strokeWidth="1" />
      <text x={padding} y={height - 2} fontSize="9" fill="#888">
        무릎각도 {min.toFixed(0)}~{max.toFixed(0)}도 · 주황 점=자동 감지된 렙 저점 · 클릭하면 이동
      </text>
    </svg>
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
  fileInputRef,
  notReadyMessage,
  onPointerDown,
  onPointerMove,
  onPointerUp,
  onReset,
  onDelete,
}) {
  return (
    <div className="pcard" style={{ maxWidth: 320, flex: '1 1 280px' }}>
      <div className="pcard-body">
        <div className="pcard-title">{label}</div>
        <input ref={fileInputRef} type="file" accept="image/*" onChange={onFile} />
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
        {imageUrl && (
          <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
            {landmarks && onReset && <button onClick={onReset}>관절 위치 원래대로 되돌리기</button>}
            {onDelete && (
              <button onClick={onDelete} style={{ color: '#e6432b' }}>
                사진 삭제
              </button>
            )}
          </div>
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
  // 삭제 후 같은 파일을 곧바로 다시 선택해도 onChange가 발생하도록, 삭제 시 이 input의
  // value를 직접 비워준다(리액트가 <input type="file">의 value를 제어할 수 없어서 필요).
  const sideFileInputRef = useRef(null)
  const frontFileInputRef = useRef(null)
  // 지금 드래그 중인 관절 정보({ which: 'side'|'front', index }) — 렌더마다 새로 만들 필요가
  // 없는 값이라 state가 아닌 ref로 관리해서 드래그 중 불필요한 리렌더를 만들지 않는다.
  const draggingRef = useRef(null)
  const { detectPose, loading } = usePoseLandmarker()

  // ---- 영상 모드 상태 ----
  // videoFrames: 추출된 프레임들의 { timestamp, landmarks, metrics } 배열. landmarks는
  // 슬라이더로 이동할 때마다 다시 인식하지 않고 그대로 재사용한다(추출 단계에서 1회만 계산).
  const [videoUrl, setVideoUrl] = useState(null)
  const [videoFrames, setVideoFrames] = useState([])
  const [videoSliderIndex, setVideoSliderIndex] = useState(0)
  const [extracting, setExtracting] = useState(false)
  const [extractProgress, setExtractProgress] = useState({ done: 0, total: 0 })
  const [videoStatus, setVideoStatus] = useState('')
  const [videoJudgeResult, setVideoJudgeResult] = useState(null)
  const [videoJudgeError, setVideoJudgeError] = useState('')
  const [videoJudging, setVideoJudging] = useState(false)
  // repBottoms: detectRepBottoms가 찾아낸 videoFrames 인덱스 목록. repResults는 렙마다
  // { index, timestamp, kneeAngle, result, error, loading } — 추출이 끝나면 사람이 슬라이더를
  // 움직이지 않아도 AI가 각 렙 저점을 알아서 판독해 여기 채워 넣는다.
  const [repBottoms, setRepBottoms] = useState([])
  const [repResults, setRepResults] = useState([])
  const videoElRef = useRef(null)
  const videoCanvasRef = useRef(null)

  // ---- 실시간 영상(웹캠) 상태 ----
  // liveFrames는 화면 표시(그래프 등)용 state. 판정 루프(liveTick)는 렌더 사이 stale
  // closure를 피하려고 liveFramesRef라는 별도 ref에 항상 최신 버퍼를 같이 들고 있다가
  // 그걸 기준으로 판단한다 — state만 쓰면 setInterval 콜백이 매번 최신값을 보장받지 못한다.
  const [liveActive, setLiveActive] = useState(false)
  const [liveStatus, setLiveStatus] = useState('')
  const [liveFrames, setLiveFrames] = useState([])
  const [liveJudgeResult, setLiveJudgeResult] = useState(null)
  const [liveJudgeError, setLiveJudgeError] = useState('')
  const liveVideoRef = useRef(null)
  const liveCanvasRef = useRef(null)
  const liveFramesRef = useRef([])
  const liveStreamRef = useRef(null)
  const liveIntervalRef = useRef(null)
  const liveOffscreenRef = useRef(null)
  const liveStartTimeRef = useRef(0)
  // 이전 틱(비동기: seek 없이 detectPose + fetch)이 아직 안 끝났는데 다음 인터벌이 도는 걸
  // 막는 가드 — 안 막으면 느린 기기에서 요청이 계속 밀려 쌓인다.
  const liveTickRunningRef = useRef(false)

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

  // 사진을 지우고 처음 상태로 되돌린다 — createObjectURL로 만든 URL은 브라우저가 자동으로
  // 회수하지 않으므로 명시적으로 해제한다(안 하면 사진을 여러 번 갈아 끼울 때마다 메모리에
  // 계속 쌓임). side를 지우면 그 사진 기준으로 받았던 판정 결과(judgeResult)도 더 이상
  // 유효하지 않으므로 함께 지운다.
  const handleDeletePhoto = (which) => () => {
    const url = which === 'side' ? sideImageUrl : frontImageUrl
    if (url) URL.revokeObjectURL(url)
    const inputEl = which === 'side' ? sideFileInputRef.current : frontFileInputRef.current
    if (inputEl) inputEl.value = ''
    if (which === 'side') {
      setSideImageUrl(null)
      setSideLandmarks(null)
      setSideOriginalLandmarks(null)
      setJudgeResult(null)
      setJudgeError('')
    } else {
      setFrontImageUrl(null)
      setFrontLandmarks(null)
      setFrontOriginalLandmarks(null)
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

  const handleVideoFile = (e) => {
    const file = e.target.files[0]
    if (!file) return
    const url = URL.createObjectURL(file)
    setVideoUrl(url)
    setVideoFrames([])
    setVideoSliderIndex(0)
    setVideoJudgeResult(null)
    setVideoJudgeError('')
    setVideoStatus('')
    setRepBottoms([])
    setRepResults([])
  }

  // AI-06(/ai/coaching/frame)에 보낼 "그 시점까지의 최근 프레임 구간"을 잘라낸다(파일 상단
  // VIDEO_JUDGE_WINDOW 주석 참고) — 실제 서비스가 매 호출마다 최근 윈도우만 보내는 것과
  // 같은 형태로 재현한다. 수동 판정(requestVideoJudgment)과 자동 렙 판독(autoJudgeReps)
  // 양쪽에서 같은 로직을 공유한다.
  const judgeWindow = (idx, frames) => {
    const start = Math.max(0, idx - VIDEO_JUDGE_WINDOW + 1)
    return frames.slice(start, idx + 1).map((f) => ({ timestamp: f.timestamp, ...f.metrics }))
  }

  const callCoachingFrame = async (angle_history) => {
    const res = await fetch(`${AI_BASE}/ai/coaching/frame`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ angle_history }),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return res.json()
  }

  // detectRepBottoms가 찾아낸 저점들을 순서대로(직렬로) 서버에 판독 요청한다. 사람이
  // 슬라이더를 움직이거나 버튼을 누르지 않아도, 추출이 끝나면 이 함수가 자동으로 호출돼
  // "가장 무릎각도가 작을 때"를 AI가 알아서 찾아 판독하는 흐름을 만든다. 병렬로 한꺼번에
  // 쏘지 않고 순차 처리하는 이유는 handleVideoLoadedMetadata와 동일(안정성 우선).
  const autoJudgeReps = async (bottoms, frames) => {
    setRepResults(
      bottoms.map((idx) => ({
        index: idx,
        timestamp: frames[idx].timestamp,
        kneeAngle: frames[idx].metrics.knee_angle,
        result: null,
        error: '',
        loading: true,
      })),
    )
    for (let r = 0; r < bottoms.length; r++) {
      try {
        const result = await callCoachingFrame(judgeWindow(bottoms[r], frames))
        setRepResults((prev) => prev.map((rep, i) => (i === r ? { ...rep, result, loading: false } : rep)))
      } catch (err) {
        setRepResults((prev) =>
          prev.map((rep, i) => (i === r ? { ...rep, error: `AI 서버 연결 실패: ${err.message}`, loading: false } : rep)),
        )
      }
    }
  }

  // 저장된 landmarks를 재사용해 해당 프레임으로 영상을 이동시키고 스켈레톤을 다시 그린다.
  // drawLandmarks는 첫 인자에서 clientWidth/clientHeight만 읽으므로 <img> 대신 <video>를
  // 그대로 넘겨도 동작한다 — 이미지 모드와 별도 그리기 함수를 만들 필요가 없었다.
  const goToVideoFrame = async (idx, frames = videoFrames) => {
    const video = videoElRef.current
    const frame = frames[idx]
    if (!video || !frame) return
    await seekVideo(video, frame.timestamp)
    requestAnimationFrame(() => drawLandmarks(video, videoCanvasRef.current, frame.landmarks))
  }

  const handleVideoSliderChange = (e) => {
    const idx = Number(e.target.value)
    setVideoSliderIndex(idx)
    goToVideoFrame(idx)
  }

  const handleSparklineSelect = (idx) => {
    setVideoSliderIndex(idx)
    goToVideoFrame(idx)
  }

  // 영상 메타데이터(길이 등)를 읽는 즉시 프레임 추출을 시작한다. 매 샘플 시점마다
  // (1) 영상을 그 시점으로 seek → (2) 축소된 오프스크린 캔버스에 그 프레임을 그림
  // (원본 해상도 그대로 MediaPipe에 넣으면 프레임마다 느려짐) → (3) 관절 인식 →
  // (4) 인식 성공한 프레임만 기록, 순서로 처리한다. 순차 처리(await를 루프 안에서)라
  // 느리긴 하지만, 같은 usePoseLandmarker 인스턴스를 병렬로 호출하는 게 안전하다는
  // 보장이 없어 안정성을 택했다 — 이 페이지는 연습/검증용이라 속도보다 정확성이 우선이다.
  const handleVideoLoadedMetadata = async () => {
    const video = videoElRef.current
    if (!video) return
    const duration = video.duration
    if (!duration || !isFinite(duration)) {
      setVideoStatus('영상 길이를 읽지 못했어요. 다른 파일로 시도해주세요.')
      return
    }

    let interval = VIDEO_SAMPLE_INTERVAL_SEC
    if (Math.ceil(duration / interval) > VIDEO_MAX_FRAMES) {
      interval = duration / VIDEO_MAX_FRAMES
    }
    const timestamps = []
    for (let t = 0; t < duration; t += interval) timestamps.push(t)
    if (timestamps.length === 0) timestamps.push(0)

    setExtracting(true)
    setVideoStatus('')
    setExtractProgress({ done: 0, total: timestamps.length })

    const offscreen = document.createElement('canvas')
    const scale = video.videoWidth > 480 ? 480 / video.videoWidth : 1
    offscreen.width = Math.round(video.videoWidth * scale)
    offscreen.height = Math.round(video.videoHeight * scale)
    const ctx = offscreen.getContext('2d')

    const frames = []
    for (let i = 0; i < timestamps.length; i++) {
      await seekVideo(video, timestamps[i])
      ctx.drawImage(video, 0, 0, offscreen.width, offscreen.height)
      const landmarks = await detectPose(offscreen)
      if (landmarks) {
        frames.push({ timestamp: timestamps[i], landmarks, metrics: buildSideMetrics(landmarks) })
      }
      setExtractProgress({ done: i + 1, total: timestamps.length })
    }

    setExtracting(false)
    if (frames.length < VIDEO_MIN_USABLE_FRAMES) {
      setVideoStatus(`관절 인식에 성공한 프레임이 너무 적어요 (${frames.length}개). 다른 영상으로 시도해주세요.`)
      setVideoFrames([])
      return
    }

    setVideoFrames(frames)

    // "가장 무릎각도가 작을 때"를 AI가 직접 찾아서 판독한다 — detectRepBottoms로 렙(들)의
    // 저점을 자동 감지하고, 곧바로 autoJudgeReps로 서버 판정까지 사람 개입 없이 진행한다.
    const bottoms = detectRepBottoms(frames)
    setRepBottoms(bottoms)
    if (bottoms.length > 0) {
      setVideoSliderIndex(bottoms[0])
      goToVideoFrame(bottoms[0], frames)
      autoJudgeReps(bottoms, frames)
    } else {
      // 저점을 하나도 못 찾았으면(예: 서 있는 자세만 찍힌 영상) 폴백으로 전체 최저점 하나만
      // 보여준다 — 자동 판독은 하지 않고, 사람이 슬라이더로 직접 확인하도록 남겨둔다.
      let deepestIdx = 0
      frames.forEach((f, idx) => {
        if (f.metrics.knee_angle < frames[deepestIdx].metrics.knee_angle) deepestIdx = idx
      })
      setVideoSliderIndex(deepestIdx)
      goToVideoFrame(deepestIdx, frames)
      setVideoStatus('무릎이 충분히 굽혀진 저점을 찾지 못했어요 — 슬라이더로 직접 시점을 골라 판정해주세요.')
    }
  }

  // 슬라이더/그래프로 고른 임의 시점을 수동으로 판정할 때 쓴다(자동 렙 판독과 별개로,
  // 특정 순간을 따로 확인하고 싶을 때를 위해 남겨둔다).
  const requestVideoJudgment = async () => {
    const frame = videoFrames[videoSliderIndex]
    if (!frame) return
    setVideoJudging(true)
    setVideoJudgeError('')
    setVideoJudgeResult(null)
    try {
      setVideoJudgeResult(await callCoachingFrame(judgeWindow(videoSliderIndex, videoFrames)))
    } catch (err) {
      setVideoJudgeError(`AI 서버 연결 실패: ${err.message} (AI 서버가 localhost:8000에서 실행 중인지 확인해주세요)`)
    } finally {
      setVideoJudging(false)
    }
  }

  // 웹캠 스트림에서 한 프레임을 뽑아 관절을 인식하고, 롤링 버퍼에 추가한 뒤 그 순간까지의
  // 최근 윈도우로 AI-06 판정을 요청한다. LIVE_SAMPLE_INTERVAL_MS마다 반복 호출된다.
  const liveTick = async () => {
    if (liveTickRunningRef.current) return // 이전 틱이 아직 처리 중이면 이번 틱은 건너뛴다
    liveTickRunningRef.current = true
    try {
      const video = liveVideoRef.current
      if (!video || video.readyState < 2) return // 아직 첫 프레임이 디코딩되기 전

      if (!liveOffscreenRef.current) liveOffscreenRef.current = document.createElement('canvas')
      const offscreen = liveOffscreenRef.current
      const scale = video.videoWidth > 480 ? 480 / video.videoWidth : 1
      const w = Math.round(video.videoWidth * scale)
      const h = Math.round(video.videoHeight * scale)
      if (offscreen.width !== w || offscreen.height !== h) {
        offscreen.width = w
        offscreen.height = h
      }
      offscreen.getContext('2d').drawImage(video, 0, 0, w, h)

      const landmarks = await detectPose(offscreen)
      if (!landmarks) return

      const timestamp = (performance.now() - liveStartTimeRef.current) / 1000
      const frame = { timestamp, landmarks, metrics: buildSideMetrics(landmarks) }
      const next = [...liveFramesRef.current, frame].slice(-LIVE_BUFFER_MAX)
      liveFramesRef.current = next
      setLiveFrames(next)
      drawLandmarks(video, liveCanvasRef.current, landmarks)

      if (next.length >= VIDEO_MIN_USABLE_FRAMES) {
        try {
          const result = await callCoachingFrame(judgeWindow(next.length - 1, next))
          setLiveJudgeResult(result)
          setLiveJudgeError('')
        } catch (err) {
          setLiveJudgeError(`AI 서버 연결 실패: ${err.message} (AI 서버가 localhost:8000에서 실행 중인지 확인해주세요)`)
        }
      }
    } finally {
      liveTickRunningRef.current = false
    }
  }

  const startLive = async () => {
    setLiveStatus('')
    setLiveJudgeError('')
    setLiveJudgeResult(null)
    liveFramesRef.current = []
    setLiveFrames([])
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' }, audio: false })
      liveStreamRef.current = stream
      const video = liveVideoRef.current
      video.srcObject = stream
      await video.play()
      liveStartTimeRef.current = performance.now()
      liveIntervalRef.current = setInterval(liveTick, LIVE_SAMPLE_INTERVAL_MS)
      setLiveActive(true)
    } catch (err) {
      setLiveStatus(`카메라를 열지 못했어요: ${err.message} (브라우저의 카메라 권한을 확인해주세요)`)
    }
  }

  const stopLive = () => {
    if (liveIntervalRef.current) {
      clearInterval(liveIntervalRef.current)
      liveIntervalRef.current = null
    }
    if (liveStreamRef.current) {
      liveStreamRef.current.getTracks().forEach((track) => track.stop())
      liveStreamRef.current = null
    }
    if (liveVideoRef.current) liveVideoRef.current.srcObject = null
    setLiveActive(false)
  }

  // 페이지를 떠날 때 카메라가 계속 켜진 채로 남지 않도록 정리한다.
  useEffect(() => {
    return () => {
      if (liveIntervalRef.current) clearInterval(liveIntervalRef.current)
      if (liveStreamRef.current) liveStreamRef.current.getTracks().forEach((track) => track.stop())
    }
  }, [])

  // 측면 랜드마크로 계산한 값 + 정면(있으면) 랜드마크로 계산한 무릎모임/비대칭 값을
  // AngleFrame 3개(타임스탬프만 다름)로 복제해 /ai/coaching/frame(AI-06)에 보낸다 — 값이
  // 동일하니 서버가 "정지" 상태로 인식해 실제 임계값 비교가 적용된다(파일 상단 주석 참고).
  //
  // (2026-08-27 추가) "정면 사진만으로도 판정이 되는지 확인해보고 싶다"는 요청에 따라,
  // 측면 사진 없이 정면 사진만 있어도 판정 요청이 가능하게 했다. knee_angle/hip_angle
  // (엉덩이-무릎-발목/어깨-엉덩이-무릎 3점 각도)은 카메라가 어느 방향을 보든 좌표 3개만
  // 있으면 계산 자체는 되는 값이라, 정면 사진에서도 buildSideMetrics()를 그대로 돌릴 수
  // 있다 — 다만 정면 사진은 앞뒤 굽힘이 카메라 축과 거의 겹쳐(원근 압축) 실제 각도보다
  // 부정확하게 나올 수 있다. shoulder_forward_lean_deg/heel_lift_ratio/
  // knee_over_toe_ratio/torso_shin_lean_gap_deg는 "몸이 향한 방향"을 발목-발끝의 좌우
  // 오프셋(facingDirection)으로 판단하는데, 정면 사진에서는 그 오프셋이 거의 0이라
  // MIN_RELIABLE_FOOT_LENGTH 게이트에 걸려 0/null로 나오는 게 정상이다 — 버그가 아니라
  // "정면 사진만으로는 이 지표들을 신뢰할 수 없다"는 걸 그대로 보여주는 것이고, 오히려
  // 이 페이지가 확인하려는 질문(정면 사진만으로 뭘 판정할 수 있고 뭘 못 하는지)에 대한
  // 답이다.
  const requestJudgment = async () => {
    if (!sideLandmarks && !frontLandmarks) return
    setJudging(true)
    setJudgeError('')
    setJudgeResult(null)
    const baseFrame = buildSideMetrics(sideLandmarks ?? frontLandmarks)
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
    <PageShell showNav={false}>
      <div className="page-eyebrow-row">
        <div className="page-index-tag">POSE TEST</div>
      </div>

      <div className="section-head">
        <div className="section-title">사진 측정 연습 페이지</div>
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
            <br />
            측면 사진 없이 정면 사진만으로도 판정 요청을 보낼 수 있어요 — 정면 사진만으로
            뭐가 판정되고 뭐가 안 되는지 확인하는 용도예요. 다만 측면 전용 지표(시선/발뒤꿈치/
            무릎-발끝/무게중심)는 정면 사진에서는 "몸이 향한 방향"을 못 구해서 대부분
            0/측정불가로 나와요 — 그건 오류가 아니라 정면 사진만으로는 그 지표들을 믿을 수
            없다는 뜻이에요. 무릎 모임/좌우 비대칭은 정면 사진 전용이라 그대로 정상 판정돼요.
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
              fileInputRef={sideFileInputRef}
              notReadyMessage="무릎/엉덩이/어깨/발뒤꿈치/무릎-발끝 측정에 쓰여요."
              onPointerDown={handlePointerDown('side')}
              onPointerMove={handlePointerMove('side')}
              onPointerUp={handlePointerUp('side')}
              onReset={sideOriginalLandmarks ? handleReset('side') : null}
              onDelete={handleDeletePhoto('side')}
            />
            <PhotoCard
              label="정면 사진 (선택)"
              imageUrl={frontImageUrl}
              landmarks={frontLandmarks}
              onFile={handleFile('front')}
              onImageLoad={handleFrontImageLoad}
              imgRef={frontImgRef}
              canvasRef={frontCanvasRef}
              fileInputRef={frontFileInputRef}
              notReadyMessage="무릎 모임/좌우 비대칭/어깨·골반 좌우 기울기 측정에 쓰여요."
              onPointerDown={handlePointerDown('front')}
              onPointerMove={handlePointerMove('front')}
              onPointerUp={handlePointerUp('front')}
              onReset={frontOriginalLandmarks ? handleReset('front') : null}
              onDelete={handleDeletePhoto('front')}
            />
          </div>

          {loading && <p className="pcard-desc" style={{ marginTop: 12 }}>분석 중...</p>}
          {status && <p className="pcard-desc" style={{ marginTop: 12 }}>{status}</p>}

          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
            <MeasurementPanel
              title={sideLandmarks ? '측면 측정값' : '측면 지표 계산값 (정면 사진 기반 — 참고용, 신뢰 불가)'}
              landmarks={sideLandmarks ?? frontLandmarks}
            />
            <FrontalMeasurementPanel landmarks={frontLandmarks} />
          </div>

          {(sideLandmarks || frontLandmarks) && (
            <button
              onClick={requestJudgment}
              disabled={judging}
              style={{ marginTop: 16 }}
            >
              {judging
                ? '판정 요청 중...'
                : sideLandmarks
                  ? 'AI 서버로 정상/이상 판정 요청'
                  : 'AI 서버로 정상/이상 판정 요청 (정면 사진만 — 측면 전용 지표는 신뢰 불가)'}
            </button>
          )}

          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
            <JudgmentPanel result={judgeResult} error={judgeError} loading={judging} />
          </div>

      <div className="section-head" style={{ marginTop: 32 }}>
        <div className="section-title">영상 측정 연습 페이지 (실험)</div>
      </div>

          <p className="pcard-desc" style={{ marginBottom: 12 }}>
            스쿼트 영상(측면)을 올리면 일정 간격으로 프레임을 뽑아 각 프레임의 관절/각도를
            계산하고, 무릎각도가 가장 작은(가장 깊이 앉은) 저점을 AI가 직접 찾아 자동으로
            판독해요 — 사람이 슬라이더를 움직이지 않아도 돼요. 영상에 렙이 여러 번 있으면
            저점마다 각각 판독합니다.
            <br />
            사진 모드는 값이 같은 프레임 3개를 복제해 "정지" 상태로 우회하지만, 영상 모드는
            실제 타임스탬프가 있는 시계열을 그대로 보내기 때문에 AI 서버가 내려가는 중/올라오는
            중/정지 단계를 실제로 어떻게 판정하는지도 확인할 수 있어요(그래프/슬라이더로 임의
            시점을 골라 수동으로 다시 확인할 수도 있어요).
            <br />
            아직 정면 영상(무릎 모임/좌우 비대칭)은 지원하지 않고 측면 영상만 지원해요.
          </p>

          <div style={{ maxWidth: 520 }}>
            <input type="file" accept="video/*" onChange={handleVideoFile} />

            {videoUrl && (
              <div style={{ position: 'relative', marginTop: 12 }}>
                <video
                  ref={videoElRef}
                  src={videoUrl}
                  onLoadedMetadata={handleVideoLoadedMetadata}
                  muted
                  playsInline
                  style={{ width: '100%', display: 'block', borderRadius: 8, background: '#000' }}
                />
                <canvas
                  ref={videoCanvasRef}
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

            {extracting && (
              <p className="pcard-desc" style={{ marginTop: 8 }}>
                프레임 추출 및 관절 인식 중... ({extractProgress.done}/{extractProgress.total})
              </p>
            )}
            {videoStatus && <p className="pcard-desc" style={{ marginTop: 8 }}>{videoStatus}</p>}

            {repResults.length > 0 && (
              <div style={{ marginTop: 12 }}>
                <div className="pcard-desc" style={{ marginBottom: 6 }}>
                  AI가 자동으로 찾은 스쿼트 저점 {repResults.length}개 — 카드를 클릭하면 그 프레임으로 이동해요.
                </div>
                <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                  {repResults.map((rep, i) => (
                    <RepResultCard
                      key={rep.index}
                      rep={rep}
                      repIndex={i}
                      active={videoSliderIndex === rep.index}
                      onClick={() => {
                        setVideoSliderIndex(rep.index)
                        goToVideoFrame(rep.index)
                      }}
                    />
                  ))}
                </div>
              </div>
            )}

            {videoFrames.length > 1 && (
              <>
                <KneeAngleSparkline
                  frames={videoFrames}
                  currentIndex={videoSliderIndex}
                  repMarkers={repBottoms}
                  onSelect={handleSparklineSelect}
                />
                <input
                  type="range"
                  min={0}
                  max={videoFrames.length - 1}
                  value={videoSliderIndex}
                  onChange={handleVideoSliderChange}
                  style={{ width: '100%', marginTop: 4 }}
                />
                <div className="pcard-desc" style={{ marginTop: 4 }}>
                  프레임 {videoSliderIndex + 1}/{videoFrames.length} ·{' '}
                  {videoFrames[videoSliderIndex].timestamp.toFixed(2)}초 · 무릎각도{' '}
                  {videoFrames[videoSliderIndex].metrics.knee_angle.toFixed(1)}도 · 엉덩이각도{' '}
                  {videoFrames[videoSliderIndex].metrics.hip_angle.toFixed(1)}도
                </div>

                <button onClick={requestVideoJudgment} disabled={videoJudging} style={{ marginTop: 12 }}>
                  {videoJudging ? '판정 요청 중...' : '이 시점까지 최근 프레임으로 AI 서버 판정 요청'}
                </button>

                <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
                  <JudgmentPanel result={videoJudgeResult} error={videoJudgeError} loading={videoJudging} />
                </div>
              </>
            )}
          </div>

      <div className="section-head" style={{ marginTop: 32 }}>
        <div className="section-title">실시간 영상 측정 연습 페이지 (웹캠, 실험)</div>
      </div>

          <p className="pcard-desc" style={{ marginBottom: 12 }}>
            나중에 실제 영상을 찍기 전에, 지금 이 컴퓨터의 웹캠으로 미리 실시간 판정을
            확인해볼 수 있어요. "실시간 시작"을 누르면 카메라 권한을 요청하고, 약{' '}
            {(LIVE_SAMPLE_INTERVAL_MS / 1000).toFixed(2)}초마다 관절을 인식해서 최근{' '}
            {VIDEO_JUDGE_WINDOW}프레임 구간을 AI 서버(AI-06)에 계속 보내요. 실제 서비스가
            웹캠으로 실시간 코칭할 때와 같은 흐름이라, 지금 판정이 얼마나 잘/빠르게 나오는지
            그대로 미리 확인하는 용도예요. 측면이 보이게 카메라를 세워두고 서 있는 상태에서
            시작해주세요.
          </p>

          <div style={{ maxWidth: 520 }}>
            <button onClick={liveActive ? stopLive : startLive}>
              {liveActive ? '실시간 중지' : '실시간 시작'}
            </button>
            {liveStatus && <p className="pcard-desc" style={{ marginTop: 8 }}>{liveStatus}</p>}

            <div style={{ position: 'relative', marginTop: 12, display: liveActive ? 'block' : 'none' }}>
              <video
                ref={liveVideoRef}
                muted
                playsInline
                style={{ width: '100%', display: 'block', borderRadius: 8, background: '#000', transform: 'scaleX(-1)' }}
              />
              <canvas
                ref={liveCanvasRef}
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  width: '100%',
                  height: '100%',
                  pointerEvents: 'none',
                  transform: 'scaleX(-1)',
                }}
              />
            </div>

            {liveActive && liveFrames.length > 0 && (
              <>
                <KneeAngleSparkline frames={liveFrames} currentIndex={liveFrames.length - 1} />
                <div className="pcard-desc" style={{ marginTop: 4 }}>
                  버퍼 {liveFrames.length}/{LIVE_BUFFER_MAX}프레임 · 무릎각도{' '}
                  {liveFrames[liveFrames.length - 1].metrics.knee_angle.toFixed(1)}도 · 엉덩이각도{' '}
                  {liveFrames[liveFrames.length - 1].metrics.hip_angle.toFixed(1)}도
                </div>
                <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
                  <JudgmentPanel result={liveJudgeResult} error={liveJudgeError} loading={false} />
                </div>
              </>
            )}
          </div>
    </PageShell>
  )
}

export default MlTestPage

import { useState } from 'react'
import './MainPage.css'
import heroPhoto from '../assets/hero-photo.webp'
import heroBg from '../assets/hero-bg.webp'
import { useAuth } from '../lib/auth.js'
import SiteNav from '../components/SiteNav.jsx'

const HERO_REVEAL_KEY = 'heroRevealedAt'
const HERO_REVEAL_TTL_MS = 30 * 60 * 1000

function wasRecentlyRevealed() {
  const lastRevealedAt = Number(localStorage.getItem(HERO_REVEAL_KEY))
  return Boolean(lastRevealedAt) && Date.now() - lastRevealedAt < HERO_REVEAL_TTL_MS
}

// 히어로 사진(hero-photo.webp, 2370x3397) 위에 얹는 자세 측정 오버레이.
// 좌표는 이 사진을 usePoseLandmarker와 같은 MediaPipe PoseLandmarker(pose_landmarker_full)로
// 실제 검출해서 나온 33개 관절 좌표를 옮긴 값 — F/B는 사진 속 앞으로 뻗은 다리·팔(front)과
// 뒤로 뻗은 다리·팔(back)을 뜻함. neck/hip은 MediaPipe에 없는 관절이라 양쪽 어깨/골반의
// 중점으로 계산해서 채움. head도 마찬가지로 없는 관절이라, 목선과 자연스럽게 이어지도록
// 양쪽 귀의 중점(귀 근처 중앙부)으로 잡음.
const POSE_KP = {
  head: [1550, 376],
  neck: [1336, 758],
  shoulderF: [1571, 827],
  shoulderB: [1102, 688],
  elbowF: [1872, 1239],
  wristF: [2164, 862],
  elbowB: [605, 926],
  wristB: [387, 1351],
  hip: [1101, 1709],
  kneeF: [1864, 1872],
  ankleF: [1327, 2336],
  footF: [1317, 2708],
  kneeB: [660, 2404],
  ankleB: [260, 3061],
  footB: [503, 3305],
}
const POSE_BONES = [
  ['head', 'neck'], ['neck', 'shoulderF'], ['neck', 'shoulderB'],
  ['shoulderF', 'elbowF'], ['elbowF', 'wristF'],
  ['shoulderB', 'elbowB'], ['elbowB', 'wristB'],
  ['neck', 'hip'],
  ['hip', 'kneeF'], ['kneeF', 'ankleF'], ['ankleF', 'footF'],
  ['hip', 'kneeB'], ['kneeB', 'ankleB'], ['ankleB', 'footB'],
]

// 각도 숫자는 오버레이 전체에 걸린 8deg 회전(.hero-pose-overlay) 안에서도 눈에는 똑바로
// 보이게, 자기 위치를 축으로 -8deg를 반대로 걸어서 상쇄함.
function AngleLabel({ cx, cy, ringR, angle, textX, textY, anchor, light }) {
  return (
    <>
      <circle className={`pose-angle-ring${light ? ' pose-angle-ring-light' : ''}`} cx={cx} cy={cy} r={ringR} />
      <text
        className={`pose-angle-text${light ? ' pose-angle-text-light' : ''}`}
        x={textX} y={textY}
        textAnchor={anchor}
        transform={`rotate(-8 ${textX} ${textY})`}
      >
        {angle}°
      </text>
    </>
  )
}

function PoseOverlay() {
  return (
    <svg
      className="hero-pose-overlay"
      viewBox="0 0 2370 3397"
      preserveAspectRatio="xMidYMid meet"
      aria-hidden="true"
    >
      {POSE_BONES.map(([a, b]) => (
        <line
          key={`${a}-${b}`}
          className="pose-bone"
          x1={POSE_KP[a][0]} y1={POSE_KP[a][1]}
          x2={POSE_KP[b][0]} y2={POSE_KP[b][1]}
        />
      ))}

      {Object.entries(POSE_KP).map(([name, [x, y]]) => (
        <circle key={name} className="pose-kp" cx={x} cy={y} r={10} />
      ))}

      {/* 무릎/팔꿈치 각도 리드아웃 - 각각 hip-knee-ankle, shoulder-elbow-wrist 세 점으로 실제
          계산한 각도(반올림). 뒷다리(kneeB) 쪽은 사진 하단부라 패널에 가려져서 뺌. */}
      <AngleLabel cx={POSE_KP.kneeF[0]} cy={POSE_KP.kneeF[1]} ringR={120} angle={53}
        textX={2009} textY={1896} anchor="start" />
      <AngleLabel cx={POSE_KP.elbowF[0]} cy={POSE_KP.elbowF[1]} ringR={100} angle={74}
        textX={2000} textY={1259} anchor="start" />
      {/* 뒷팔 쪽은 팔뼈 두 개가 겹쳐 지나가는 자리라 기본 빨강이면 뼈 선에 묻혀서 흰색으로 */}
      <AngleLabel cx={POSE_KP.elbowB[0]} cy={POSE_KP.elbowB[1]} ringR={100} angle={143}
        textX={490} textY={959} anchor="end" light />
    </svg>
  )
}

function MainPage() {
  const [revealed, setRevealed] = useState(wasRecentlyRevealed)
  const { user, handleLogout } = useAuth()

  const handleReveal = () => {
    setRevealed(true)
    localStorage.setItem(HERO_REVEAL_KEY, String(Date.now()))
  }

  return (
    <div className={`app${revealed ? ' revealed' : ''}`}>
      <main className="main">
        <section
          className={`hero${revealed ? ' revealed' : ''}`}
          onClick={handleReveal}
        >
          <div className="hero-content">
            <h1
              className="hero-title"
              style={{ '--panorama-1': `url(${heroBg})` }}
            >
              WELLMADE<br />YOURSELF
            </h1>
            <p className="hero-reveal-hint">아무 곳이나 클릭하세요</p>
          </div>

          <div className="hero-panel">
            <div className="hero-nav">
              <SiteNav user={user} onLogout={handleLogout} />
            </div>

            <div className="hero-visual">
              <div className="hero-red-band"></div>
              <p className="hero-tagline-lines">
                <span className="hero-tagline-small">For a</span>Better
              </p>
              <p className="hero-tagline-big">Tomorrow</p>
              <div className="hero-photo-wrap">
                <img src={heroPhoto} alt="" className="hero-photo-tint" />
                <img src={heroPhoto} alt="" className="hero-photo-base" />
                <PoseOverlay />
              </div>
            </div>
          </div>
        </section>
      </main>
    </div>
  )
}

export default MainPage

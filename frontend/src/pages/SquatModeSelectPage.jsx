/**
 * 자세 측정 진입 화면(/exercises) — 서비스 흐름도의 "② 코칭 모드 선택".
 *
 * (2026-09-03 재작업) 사용자가 준 와이어프레임 그대로: 선택된 운동 사진이 콘텐츠 영역
 * 전체를 여백 없이 꽉 채우고(PageShell의 bleed 옵션), 그 위 오른쪽에 반투명 흰 패널이
 * 뜬다 — 패널 맨 위 빨간 띠, 그 아래 [운동 드롭다운 + "운동 방법" 버튼] 한 줄, 그 아래
 * 큰 카드 두 개(사진 코칭 / 실시간 코칭). 와이어프레임에서 각 요소 옆에 적혀 있던 회색
 * 글씨("Dropdown", "사진 코칭", "라이브코칭")는 요소를 가리키는 주석이라 UI로 만들지
 * 않는다 — 카드 안에 같은 문구가 이미 들어가므로 중복이 된다.
 *
 * 배경 사진은 고정 크롭 이미지가 아니라 `object-fit: cover` + 운동별 `object-position`으로
 * 채운다 — 사용자마다 창 크기가 달라 고정 크롭으로는 프레이밍이 깨지기 때문. 사진 자체는
 * 사용자가 직접 잘라 준 것을 그대로 쓴다(assets/exercises/*.jpg).
 *
 * 운동 드롭다운은 스쿼트/런지/플랭크 세 개를 보여주지만(components/ExerciseSelectDropdown.jsx),
 * 실제 AI 판정 로직(ai/app/pose/rules.py, DTW, LLM 검증)은 전부 스쿼트 전용이다.
 * (2026-09-07 변경) 런지/플랭크를 고르면 배경 사진만 바뀌고, 모달 대신 패널 바로 밑에
 * "준비중입니다" 안내 박스(.exercise-notice)가 뜬다 — 예전엔 드롭다운 선택만으로도
 * 모달이 튀어나왔는데, 사용자 피드백에 따라 그건 없애고 안내문으로 대체했다. 모달은
 * 사진 코칭/실시간 코칭 타일을 실제로 눌렀을 때만 뜬다(READY_EXERCISES, handleModeLinkClick 참고).
 */

import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import PageShell from '../components/PageShell.jsx'
import Modal from '../components/Modal.jsx'
import ExerciseSelectDropdown from '../components/ExerciseSelectDropdown.jsx'
import ExerciseGuideModal from '../components/ExerciseGuideModal.jsx'
import photoCoachingIcon from '../assets/icons/photo-coaching-icon.svg'
import liveCoachingIcon from '../assets/icons/live-coaching-icon.svg'
import squatPhoto from '../assets/exercises/squat-photo.jpg'
import lungePhoto from '../assets/exercises/lunge-photo.jpg'
import plankPhoto from '../assets/exercises/plank-photo.jpg'
import './squatShared.css'
import './SquatModeSelectPage.css'

// 운동별 배경 사진 + object-position(사람이 화면 왼쪽~중앙, 오른쪽은 패널이 놓일 빈 공간).
const EXERCISE_BACKGROUNDS = {
  squat: { image: squatPhoto, position: '32% 42%', label: '스쿼트' },
  lunge: { image: lungePhoto, position: '38% 55%', label: '런지' },
  plank: { image: plankPhoto, position: '26% 62%', label: '플랭크' },
}

// 패널 안 큰 버튼 두 개 — 2026-09-03 레이아웃 재작업 이전의 "모드 선택 카드"(이미지 +
// 제목 + 설명)를 그대로 되살린 것(사용자 요청: "예전에 있던 버튼을 넣어줘"). 카드 전체가
// 링크다. 이미지는 처음엔 스크린샷/placeholder였다가, "지금 아이콘 너무 못생겼다"는
// 피드백에 따라 같은 날 다시 간단한 선형(라인) 아이콘 배지로 바꿨다(assets/icons/*.svg).
const MODE_CARDS = [
  {
    to: '/exercises/photo',
    title: '사진 코칭',
    desc: '스쿼트 자세를 사진 한 장으로 찍으면, 관절 좌표를 표시하고 그 자리에서 정상/이상 여부와 교정 포인트를 알려드려요.',
    image: photoCoachingIcon,
  },
  {
    to: '/exercises/live',
    title: '실시간 코칭',
    desc: '웹캠을 켜두고 스쿼트를 하면, 동작 중에 실시간으로 자세를 확인해서 음성으로 바로바로 코칭해드려요.',
    image: liveCoachingIcon,
  },
]

// 실제 사진/실시간 코칭이 동작하는 운동만 여기 넣는다 — 지금은 스쿼트뿐.
const READY_EXERCISES = new Set(['squat'])

function ComingSoonModal({ exerciseLabel, onClose }) {
  return (
    <Modal onClose={onClose} closeOnBackdropClick>
      <div className="modal-title">{exerciseLabel} 코칭</div>
      <p className="modal-sub" style={{ marginBottom: 0 }}>
        {exerciseLabel} 코칭은 아직 준비중입니다. 지금은 스쿼트만 사진/실시간 코칭을 이용하실 수 있어요.
      </p>
    </Modal>
  )
}

function SquatModeSelectPage() {
  const [guideOpen, setGuideOpen] = useState(false)
  const [exercise, setExercise] = useState('squat')
  const [comingSoonOpen, setComingSoonOpen] = useState(false)

  const isReady = READY_EXERCISES.has(exercise)
  const bg = EXERCISE_BACKGROUNDS[exercise] ?? EXERCISE_BACKGROUNDS.squat

  // 배경 사진 크로스페이드(2026-09-07 추가): 운동이 바뀌어도 사진이 뚝 끊기지 않고
  // 겹쳐서 부드럽게 전환되도록, 최근 사진을 레이어로 쌓아두고 위에 얹은 새 레이어를
  // opacity 0 → 1로 페이드인한다. 전환이 끝나면(약 0.45초) 오래된 레이어를 정리한다.
  const [bgLayers, setBgLayers] = useState(() => [{ id: 0, image: bg.image, position: bg.position, active: true }])
  const nextLayerId = useRef(1)

  useEffect(() => {
    const id = nextLayerId.current++
    setBgLayers((layers) => [...layers, { id, image: bg.image, position: bg.position, active: false }])

    // 두 프레임 뒤에 active를 켜야 브라우저가 opacity:0 상태를 먼저 그린 뒤 전환을 재생한다.
    const rafIds = []
    rafIds.push(
      requestAnimationFrame(() => {
        rafIds.push(
          requestAnimationFrame(() => {
            setBgLayers((layers) => layers.map((l) => (l.id === id ? { ...l, active: true } : l)))
          }),
        )
      }),
    )

    const timer = setTimeout(() => {
      setBgLayers((layers) => layers.filter((l) => l.id === id))
    }, 500)

    return () => {
      rafIds.forEach((raf) => cancelAnimationFrame(raf))
      clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [exercise])

  // (2026-09-07 추가) 운동을 바꾸면 이전에 떠 있던 "준비중" 모달을 항상 닫는다 —
  // 안 닫으면 예: 런지에서 모달을 띄운 채로 스쿼트로 바꿨을 때, 모달 문구만
  // bg.label을 다시 읽어서 "스쿼트 코칭은 준비중입니다"로 잘못 남는 버그가 있었다.
  useEffect(() => {
    setComingSoonOpen(false)
  }, [exercise])

  const handleExerciseChange = (id) => {
    setExercise(id)
  }

  const handleModeLinkClick = (e) => {
    if (isReady) return
    e.preventDefault()
    setComingSoonOpen(true)
  }

  return (
    <PageShell bleed>
      <div className="exercise-hero">
        {bgLayers.map((layer) => (
          <img
            key={layer.id}
            src={layer.image}
            alt=""
            className={`exercise-hero-bg${layer.active ? ' is-visible' : ''}`}
            style={{ objectPosition: layer.position }}
          />
        ))}

        <div className="exercise-panel-stack">
          <div className="exercise-panel">
            <div className="exercise-panel-bar">coaching</div>
            <div className="exercise-panel-body">
              <div className="exercise-panel-row">
                <ExerciseSelectDropdown value={exercise} onChange={handleExerciseChange} />
                <button
                  type="button"
                  className="exercise-panel-guide-btn"
                  onClick={() => {
                    if (isReady) {
                      setGuideOpen(true)
                    } else {
                      setComingSoonOpen(true)
                    }
                  }}
                >
                  운동 방법
                </button>
              </div>

              {MODE_CARDS.map((mode) => (
                <Link
                  key={mode.to}
                  to={mode.to}
                  className="exercise-mode-tile"
                  onClick={handleModeLinkClick}
                >
                  <img src={mode.image} alt="" className="exercise-mode-tile-img" />
                  <div className="exercise-mode-tile-title">{mode.title}</div>
                  <p className="exercise-mode-tile-desc">{mode.desc}</p>
                </Link>
              ))}
            </div>
          </div>

          {!isReady && (
            <div className="exercise-notice">
              {bg.label} 코칭은 아직 준비중입니다.
              <br />
              지금은 스쿼트만 사진/실시간 코칭을 이용하실 수 있어요.
            </div>
          )}
        </div>
      </div>

      {guideOpen && <ExerciseGuideModal onClose={() => setGuideOpen(false)} />}
      {comingSoonOpen && (
        <ComingSoonModal exerciseLabel={bg.label} onClose={() => setComingSoonOpen(false)} />
      )}
    </PageShell>
  )
}

export default SquatModeSelectPage

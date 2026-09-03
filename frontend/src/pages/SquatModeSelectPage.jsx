/**
 * 자세 측정(스쿼트 코칭) 진입 화면 — 서비스 흐름도의 "② 코칭 모드 선택".
 *
 * 사진 코칭(②-A)과 실시간 코칭(②-B) 중 하나를 고르는 카드 2개만 보여준다. 카드 전체가
 * 링크라 어디를 눌러도 이동한다(2026-09-02, 디자인 시안 반영: 번호 없이, 이미지·제목·
 * 설명을 가운데 정렬, 버튼 없이 카드 전체 클릭). "자세 측정" 섹션 타이틀 텍스트는 피드백에
 * 따라 뺐다. "POSTURE COACHING" 태그(page-eyebrow-row)는 다른 페이지와 같은 원래
 * 자리(맨 위, 세로 중앙 정렬 대상 밖)에 그대로 두고, 카드 2개(mode-select-row)만 그
 * 아래 남은 공간 안에서 세로/가로 가운데로 오도록 했다. 이미지는 실제 일러스트가 나오기
 * 전까지 쓰는 임시 플레이스홀더라, 나중에 실제 이미지로 바꿀 때는 이 파일의 import
 * 경로만 실제 이미지 파일로 바꾸면 된다. 실제 촬영/판정 화면은 각각 PhotoCoachingPage /
 * SquatCoachingPage가 담당한다.
 *
 * (2026-09-03 추가) 운동 선택 드롭다운 + "운동방법" 버튼을 PhotoCoachingPage
 * 헤더에서 이 화면 헤더로 옮겨왔다 — 사진모드/동영상모드 중 아무 데나 들어가서
 * 일일이 누르지 않아도, 모드를 고르기 전에 여기서 한 번만 운동을 고르고 운동방법도
 * 볼 수 있게 하기 위함. 두 모드가 공유하는 화면이라 여기 하나에만 있으면 된다.
 * 관련 CSS(.photo-header-actions/.exercise-dropdown 계열/.photo-guide-btn)는
 * PhotoCoachingPage.css에서 squatShared.css(공용)로 함께 옮겼다.
 *
 * (2026-09-03 추가) "사진 코칭" 카드 이미지를 임시 SVG 플레이스홀더
 * (photo-coaching-placeholder.svg)에서 사용자가 올린 실제 사진 코칭 페이지
 * 스크린샷(photo-coaching-preview.png)으로 교체했다.
 */

import { useState } from 'react'
import { Link } from 'react-router-dom'
import PageShell from '../components/PageShell.jsx'
import ExerciseSelectDropdown from '../components/ExerciseSelectDropdown.jsx'
import ExerciseGuideModal from '../components/ExerciseGuideModal.jsx'
import photoPlaceholder from '../assets/photo-coaching-preview.png'
import livePlaceholder from '../assets/live-coaching-placeholder.svg'
import './squatShared.css'
import './SquatModeSelectPage.css'

const MODES = [
  {
    to: '/squat/photo',
    title: '사진 코칭',
    desc: '스쿼트 자세를 사진 한 장으로 찍으면, 관절 좌표를 표시하고 그 자리에서 정상/이상 여부와 교정 포인트를 알려드려요.',
    image: photoPlaceholder,
  },
  {
    to: '/squat/live',
    title: '실시간 코칭',
    desc: '웹캠을 켜두고 스쿼트를 하면, 동작 중에 실시간으로 자세를 확인해서 음성으로 바로바로 코칭해드려요.',
    image: livePlaceholder,
  },
]

function SquatModeSelectPage() {
  const [guideOpen, setGuideOpen] = useState(false)

  return (
    <PageShell>
      <div className="mode-select-shell">
        <div className="page-eyebrow-row">
          <div className="page-index-tag">POSTURE COACHING</div>
          <div className="photo-header-actions">
            <ExerciseSelectDropdown value="squat" />
            <button type="button" className="squat-btn squat-btn-outline photo-guide-btn" onClick={() => setGuideOpen(true)}>
              운동방법
            </button>
          </div>
        </div>

        <div className="mode-select-center">
          <div className="mode-select-row">
            {MODES.map((mode) => (
              <Link key={mode.to} to={mode.to} className="mode-card">
                <img src={mode.image} alt={mode.title} className="mode-card-img" />
                <div className="mode-card-title">{mode.title}</div>
                <p className="mode-card-desc">{mode.desc}</p>
              </Link>
            ))}
          </div>
        </div>
      </div>

      {guideOpen && <ExerciseGuideModal onClose={() => setGuideOpen(false)} />}
    </PageShell>
  )
}

export default SquatModeSelectPage

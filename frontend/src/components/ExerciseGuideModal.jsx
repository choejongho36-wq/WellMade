/**
 * "운동방법" 모달 — 사진 코칭 페이지 상단의 운동 선택 드롭다운 옆 "운동방법" 버튼을 누르면
 * 뜬다(2026-09-02 시안: 좌측에 스쿼트 참고 사진, 우측에 번호가 매겨진 스쿼트 하는 방법
 * 5단계 + 하단 주의사항).
 *
 * 공용 Modal.jsx(Esc/포커스 트랩/× 버튼)를 그대로 쓰되, 기본 320px 모달보다 훨씬 넓은
 * 2단(사진/설명) 레이아웃이 필요해 className="exercise-guide-modal"로 폭만 오버라이드한다
 * (NutrientDetailModal.css가 같은 방식으로 .modal 기본값을 덮어쓰는 것과 동일한 패턴).
 *
 * 좌측 참고 사진은 이 세션에서 실제로 뽑은 스쿼트 랜드마크 시각화 사진(2026-09-02, 사용자가
 * 올린 사진을 640x640 JPEG로 축소해 assets에 넣었다 — lib/squatPose.js의 KEY_LANDMARKS와
 * 동일한 관절을 pink/blue로 표시한 것)을 쓴다. 원래 있던 임시 막대인간 SVG
 * 플레이스홀더(squat-guide-reference.svg)는 삭제하고 이걸로 교체했다.
 *
 * 스텝 문구는 무릎 각도 등 AI 판정에 쓰이는 실제 임곗값(ai/app/pose/rules.py)과 다른
 * 숫자를 단정적으로 제시하지 않도록, "약 90도가 기준" 같은 구체적 판정 기준값 대신 일반적인
 * 스쿼트 자세 요령(무릎/발끝 방향, 발뒤꿈치, 허리, 시선)만 담았다 — 2026-09-02 검수 항목.
 * 운동이 여러 개로 늘어날 걸 대비해 STEPS를 운동별로 분리할 수 있게 상수로 뺐다(지금은
 * 스쿼트 하나뿐).
 */

import Modal from './Modal.jsx'
import squatGuideReference from '../assets/squat-guide-reference.jpg'
import './ExerciseGuideModal.css'

const SQUAT_STEPS = [
  {
    title: '시작 자세 잡기',
    desc: '발을 어깨너비로 벌리고 발끝을 살짝 바깥으로 향하게 섭니다. 가슴을 펴고 코어에 살짝 힘을 준 상태로 준비합니다.',
  },
  {
    title: '엉덩이부터 뒤로 빼며 앉기',
    desc: '무릎과 고관절을 동시에 굽히면서 엉덩이를 뒤로 빼듯이 앉습니다. 무릎이 발끝과 같은 방향을 향하도록 유지합니다.',
  },
  {
    title: '무리 없는 만큼 깊이 앉기',
    desc: '허벅지가 바닥과 평행해지는 정도를 목표로, 무릎에 무리가 가지 않는 선에서 앉습니다. 무릎이 발끝을 크게 넘지 않도록 합니다.',
  },
  {
    title: '허리와 시선 유지하기',
    desc: '허리는 곧게 펴고, 발뒤꿈치는 바닥에서 떨어지지 않게 합니다. 시선은 정면을 편안하게 유지하고 고개가 앞으로 툭 떨어지지 않도록 합니다.',
  },
  {
    title: '발바닥으로 밀어내며 일어서기',
    desc: '발바닥 전체(특히 발뒤꿈치)로 바닥을 밀어내며 천천히 일어섭니다. 일어서는 동안에도 무릎이 안쪽으로 모이지 않게 유지합니다.',
  },
]

function ExerciseGuideModal({ onClose }) {
  return (
    <Modal onClose={onClose} className="exercise-guide-modal">
      <div className="guide-modal-body">
        <div className="guide-modal-photo">
          <img src={squatGuideReference} alt="스쿼트 앉은 자세에서 관절 좌표를 표시한 참고 사진" />
        </div>
        <div className="guide-modal-text">
          <div className="guide-modal-eyebrow">EXERCISE GUIDE</div>
          <h2 className="guide-modal-title">스쿼트 운동방법</h2>

          <ol className="guide-modal-steps">
            {SQUAT_STEPS.map((step, i) => (
              <li key={i}>
                <span className="guide-step-num">{i + 1}</span>
                <div>
                  <div className="guide-step-title">{step.title}</div>
                  <p className="guide-step-desc">{step.desc}</p>
                </div>
              </li>
            ))}
          </ol>

          <div className="guide-modal-caution">
            <b>촬영 전 확인해주세요.</b> 옆모습(측면)이 잘 보이도록 촬영해야 AI가 무릎·엉덩이
            각도를 정확히 분석할 수 있어요. 무릎/허리 등에 통증이 있다면 무리해서 동작을
            따라 하지 말고, 트레이너 등 전문가와 먼저 상담해주세요.
          </div>
        </div>
      </div>
    </Modal>
  )
}

export default ExerciseGuideModal

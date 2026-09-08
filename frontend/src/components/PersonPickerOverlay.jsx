/**
 * 사진 코칭 업로드 시 한 사진에서 여러 명이 인식됐을 때(usePhotoCoachingSession.js의
 * phase === 'choosing') 보여주는 "누구를 분석할지 고르는" 오버레이 (2026-09-03).
 *
 * PhotoLandmarkEditor와 마찬가지로 <img> 위에 절대 위치로 겹치는 방식을 쓰지만, 여기서는
 * 점 하나하나가 아니라 사람 1명 전체를 감싸는 사각 테두리(그 사람의 33개 랜드마크
 * 최소/최대 x,y로 계산한 바운딩 박스)를 그린다. 테두리를 클릭하면 onChoose(index)를
 * 불러 그 사람으로 확정한다 — 이후 흐름은 기존 1명 인식 때와 완전히 동일(좌표점 드래그
 * 화면으로 전환).
 */

import { imageToBoxPoint } from '../lib/squatPose.js'
import './PersonPickerOverlay.css'

// 여유 없이 딱 맞게 테두리를 그리면 사람 윤곽(머리카락/팔 끝 등)이 살짝 잘려 보일 수 있어
// 사방으로 3%p 정도 여백을 준다.
const BOX_PADDING = 0.03

function boundingBox(landmarks) {
  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity
  for (const { x, y } of landmarks) {
    if (x < minX) minX = x
    if (x > maxX) maxX = x
    if (y < minY) minY = y
    if (y > maxY) maxY = y
  }
  return {
    minX: Math.max(0, minX - BOX_PADDING),
    minY: Math.max(0, minY - BOX_PADDING),
    maxX: Math.min(1, maxX + BOX_PADDING),
    maxY: Math.min(1, maxY + BOX_PADDING),
  }
}

function PersonPickerOverlay({ photoUrl, alt, candidates, imageAspect, onChoose }) {
  return (
    <div className="person-picker">
      <img src={photoUrl} alt={alt} className="person-picker-img" draggable={false} />
      <div className="person-picker-notice">여러 명이 인식됐어요. 분석할 사람을 선택해주세요.</div>
      {candidates.map((landmarks, index) => {
        const { minX, minY, maxX, maxY } = boundingBox(landmarks)
        const topLeft = imageToBoxPoint(minX, minY, imageAspect)
        const bottomRight = imageToBoxPoint(maxX, maxY, imageAspect)
        return (
          <button
            key={index}
            type="button"
            className="person-picker-box"
            style={{
              left: `${topLeft.x * 100}%`,
              top: `${topLeft.y * 100}%`,
              width: `${(bottomRight.x - topLeft.x) * 100}%`,
              height: `${(bottomRight.y - topLeft.y) * 100}%`,
            }}
            onClick={() => onChoose(index)}
            aria-label={`${index + 1}번 사람 선택`}
          >
            <span className="person-picker-badge">{index + 1}</span>
          </button>
        )
      })}
    </div>
  )
}

export default PersonPickerOverlay

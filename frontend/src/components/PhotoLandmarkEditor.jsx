/**
 * 사진 코칭의 "드래그 가능한 좌표 점" 오버레이 (2026-09-02).
 *
 * 예전엔 업로드한 사진 위에 스켈레톤을 캔버스에 통째로 구워서(renderPhotoWithSkeleton)
 * 정적 이미지로만 보여줬는데, "좌표를 움직일 수 있게 해줘" 요청으로 사진은 <img> 그대로
 * 두고 그 위에 점(관절)·선(스켈레톤)을 절대 위치 오버레이로 따로 그리는 방식으로
 * 바꿨다 — 그래야 점 하나하나를 pointer 이벤트로 드래그할 수 있다.
 *
 * 미리보기 박스는 3:2로 고정하고(PhotoCoachingPage.css의 .preview-photo-box), 사진은
 * object-fit: contain으로 잘리지 않고 전체가 보이도록 표시한다(2026-09-02 — 한때
 * cover(크롭) 방식으로 바꿨었는데, "사진 자르지 말고 세로든 가로든 박스 안에 꽉 차게
 * 보이게 해달라"는 요청으로 다시 contain(여백) 방식으로 되돌림). 박스 비율과 안 맞는
 * 나머지 공간은 여백으로 남는다. 점과 선은 원본 사진 기준 정규화 좌표(0~1)를 그대로
 * 들고 있다가 squatPose.js의 imageToBoxPoint로 "박스 기준" 좌표로 바꿔서 그린다. 드래그로
 * 옮길 때는 반대로 boxToImagePoint로 박스 좌표 → 원본 사진 좌표로 되돌린다.
 *
 * AI가 잘못 찍은 좌표를 사용자가 손으로 고칠 수 있게 하되, "옮길 때마다 재계산"이
 * 아니라 "옮기고 분석 버튼을 눌러야 재계산"하는 흐름(2026-09-02 확인)이라, 이 컴포넌트는
 * 로컬 좌표 상태만 바꾸고(onPointsChange) 실제 각도 재계산은 상위(usePhotoCoachingSession의
 * runAnalysis)가 분석 버튼 클릭 시에만 담당한다.
 *
 * (2026-09-03 추가) "업로드 시 나오는 캔버스가 MlTestPage.jsx 테스트 페이지의 랜드마크
 * 그리기와 다르게 보인다"는 지적으로, 점 옆에 관절 이름 라벨을 추가하고(신뢰도 0.5 미만이면
 * MlTestPage.jsx와 동일하게 이름 뒤에 " ?"를 붙임), 점 스타일(테두리 색, 신뢰도에 따른
 * 불투명도)과 점 색상(PHOTO_DOT_LEFT_COLOR/RIGHT_COLOR, squatPose.js)을 그 페이지와
 * 동일하게 맞췄다. 다만 이 컴포넌트는 여전히 canvas가 아니라 HTML/CSS 절대 위치 오버레이
 * 방식을 유지한다 — 라벨/점이 pointer 이벤트로 드래그 가능해야 하기 때문(위 설명 참고).
 */

import { Fragment, useCallback, useRef } from 'react'
import { SKELETON_CONNECTIONS, boxToImagePoint, imageToBoxPoint } from '../lib/squatPose.js'
import './PhotoLandmarkEditor.css'

function PhotoLandmarkEditor({ photoUrl, alt, points, imageAspect, onPointsChange, leftColor, rightColor, disabled = false }) {
  const containerRef = useRef(null)
  const dragNameRef = useRef(null)

  const clientToImagePoint = useCallback(
    (clientX, clientY) => {
      const rect = containerRef.current.getBoundingClientRect()
      const bx = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width))
      const by = Math.max(0, Math.min(1, (clientY - rect.top) / rect.height))
      return boxToImagePoint(bx, by, imageAspect)
    },
    [imageAspect],
  )

  const handlePointerMove = useCallback(
    (e) => {
      const name = dragNameRef.current
      if (!name) return
      const { x, y } = clientToImagePoint(e.clientX, e.clientY)
      onPointsChange({ ...points, [name]: { ...points[name], x, y } })
    },
    [points, onPointsChange, clientToImagePoint],
  )

  const stopDrag = useCallback(() => {
    dragNameRef.current = null
    window.removeEventListener('pointermove', handlePointerMove)
    window.removeEventListener('pointerup', stopDrag)
  }, [handlePointerMove])

  const startDrag = useCallback(
    (e, name) => {
      if (disabled) return
      e.preventDefault()
      dragNameRef.current = name
      window.addEventListener('pointermove', handlePointerMove)
      window.addEventListener('pointerup', stopDrag)
    },
    [disabled, handlePointerMove, stopDrag],
  )

  return (
    <div className="landmark-editor" ref={containerRef}>
      <img src={photoUrl} alt={alt} className="landmark-editor-img" draggable={false} />
      <svg className="landmark-editor-lines" viewBox="0 0 100 100" preserveAspectRatio="none">
        {SKELETON_CONNECTIONS.map(([a, b]) => {
          const pa = points[a]
          const pb = points[b]
          if (!pa || !pb) return null
          const boxA = imageToBoxPoint(pa.x, pa.y, imageAspect)
          const boxB = imageToBoxPoint(pb.x, pb.y, imageAspect)
          return (
            <line
              key={`${a}-${b}`}
              x1={boxA.x * 100}
              y1={boxA.y * 100}
              x2={boxB.x * 100}
              y2={boxB.y * 100}
              stroke={a.startsWith('left') ? leftColor : rightColor}
              strokeWidth={0.6}
            />
          )
        })}
      </svg>
      {Object.entries(points).map(([name, p]) => {
        const boxP = imageToBoxPoint(p.x, p.y, imageAspect)
        const visibility = p.visibility ?? 1
        // MlTestPage.jsx의 drawLandmarks()와 동일한 규칙 — 신뢰도가 낮으면 이름 뒤에
        // " ?"를 붙여 표시(버그 아님, 의도된 표시).
        const suffix = visibility < 0.5 ? ' ?' : ''
        const color = name.startsWith('left') ? leftColor : rightColor
        return (
          <Fragment key={name}>
            <button
              type="button"
              className="landmark-dot"
              style={{
                left: `${boxP.x * 100}%`,
                top: `${boxP.y * 100}%`,
                background: color,
                opacity: Math.max(visibility, 0.25),
                cursor: disabled ? 'default' : 'grab',
              }}
              onPointerDown={(e) => startDrag(e, name)}
              aria-label={`${name} 좌표 (드래그로 위치 수정 가능)`}
            />
            <span
              className="landmark-label"
              style={{
                left: `${boxP.x * 100}%`,
                top: `${boxP.y * 100}%`,
              }}
            >
              {name}
              {suffix}
            </span>
          </Fragment>
        )
      })}
    </div>
  )
}

export default PhotoLandmarkEditor

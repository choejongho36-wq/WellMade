/**
 * 사진 코칭의 "드래그 가능한 좌표 점" 오버레이 (2026-09-02).
 *
 * 예전엔 업로드한 사진 위에 스켈레톤을 캔버스에 통째로 구워서(renderPhotoWithSkeleton)
 * 정적 이미지로만 보여줬는데, "좌표를 움직일 수 있게 해줘" 요청으로 사진은 <img> 그대로
 * 두고 그 위에 점(관절)·선(스켈레톤)을 절대 위치 오버레이로 따로 그리는 방식으로
 * 바꿨다 — 그래야 점 하나하나를 pointer 이벤트로 드래그할 수 있다.
 *
 * 좌표는 정규화(0~1) 값 그대로 들고 있다가 CSS %(점)와 SVG viewBox 0 0 100 100(선)에
 * 그대로 꽂아 넣는다 — 컨테이너의 실제 렌더링 크기와 무관하게 각 축(가로/세로)별로
 * 독립적으로 비율 계산되므로, <img>가 어떤 종횡비로 렌더링되든 점과 선이 항상 같은
 * 위치를 가리킨다(둘 다 같은 방식의 % 기반이라 서로 어긋나지 않음).
 *
 * AI가 잘못 찍은 좌표를 사용자가 손으로 고칠 수 있게 하되, "옮길 때마다 재계산"이
 * 아니라 "옮기고 분석 버튼을 눌러야 재계산"하는 흐름(2026-09-02 확인)이라, 이 컴포넌트는
 * 로컬 좌표 상태만 바꾸고(onPointsChange) 실제 각도 재계산은 상위(usePhotoCoachingSession의
 * runAnalysis)가 분석 버튼 클릭 시에만 담당한다.
 */

import { useCallback, useRef } from 'react'
import { SKELETON_CONNECTIONS } from '../lib/squatPose.js'
import './PhotoLandmarkEditor.css'

function PhotoLandmarkEditor({ photoUrl, alt, points, onPointsChange, leftColor, rightColor, disabled = false }) {
  const containerRef = useRef(null)
  const dragNameRef = useRef(null)

  const clientToNormalized = useCallback((clientX, clientY) => {
    const rect = containerRef.current.getBoundingClientRect()
    const x = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width))
    const y = Math.max(0, Math.min(1, (clientY - rect.top) / rect.height))
    return { x, y }
  }, [])

  const handlePointerMove = useCallback(
    (e) => {
      const name = dragNameRef.current
      if (!name) return
      const { x, y } = clientToNormalized(e.clientX, e.clientY)
      onPointsChange({ ...points, [name]: { ...points[name], x, y } })
    },
    [points, onPointsChange, clientToNormalized],
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
          return (
            <line
              key={`${a}-${b}`}
              x1={pa.x * 100}
              y1={pa.y * 100}
              x2={pb.x * 100}
              y2={pb.y * 100}
              stroke={a.startsWith('left') ? leftColor : rightColor}
              strokeWidth={0.6}
            />
          )
        })}
      </svg>
      {Object.entries(points).map(([name, p]) => (
        <button
          key={name}
          type="button"
          className="landmark-dot"
          style={{
            left: `${p.x * 100}%`,
            top: `${p.y * 100}%`,
            background: name.startsWith('left') ? leftColor : rightColor,
            cursor: disabled ? 'default' : 'grab',
          }}
          onPointerDown={(e) => startDrag(e, name)}
          aria-label={`${name} 좌표 (드래그로 위치 수정 가능)`}
        />
      ))}
    </div>
  )
}

export default PhotoLandmarkEditor

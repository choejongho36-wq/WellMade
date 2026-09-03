/**
 * 사진 업로드 직후, 포즈 인식을 돌리기 전에 먼저 보여주는 "자르기" 화면 (2026-09-03).
 *
 * PhotoLandmarkEditor/PersonPickerOverlay와 같은 패턴 — 원본 사진 위에 절대 위치
 * 오버레이를 얹고, boxToImagePoint/imageToBoxPoint(squatPose.js)로 "박스 기준 좌표"와
 * "원본 사진 기준 정규화 좌표(0~1)"를 서로 변환한다. cropRect는 항상 원본 사진 기준
 * 정규화 좌표({x, y, width, height})로 들고 있다가, 실제 자르기는 usePhotoCoachingSession.js
 * 쪽에서 이 값을 픽셀 좌표로 바꿔 canvas로 그려낸다(이 컴포넌트는 좌표만 다루고, 실제
 * 이미지 처리는 하지 않는다).
 *
 * 네 모서리 손잡이를 드래그하면 반대쪽 모서리를 고정한 채 크기를 다시 계산하고
 * (MIN_CROP_SIZE보다 작아지지 않게 방어), 사각형 내부를 드래그하면 위치만 옮긴다.
 */

import { useCallback, useRef } from 'react'
import { boxToImagePoint, imageToBoxPoint } from '../lib/squatPose.js'
import './PhotoCropOverlay.css'

const MIN_CROP_SIZE = 0.08 // 정규화 좌표 기준 최소 너비/높이 — 너무 작아지는 것 방지
const CORNERS = ['nw', 'ne', 'sw', 'se']

function clamp(v, min, max) {
  return Math.min(max, Math.max(min, v))
}

function PhotoCropOverlay({ photoUrl, alt, imageAspect, cropRect, onCropRectChange, onApply, onSkip }) {
  const containerRef = useRef(null)
  const dragRef = useRef(null) // { mode: 'move' | 'nw' | 'ne' | 'sw' | 'se', ... }

  const clientToImagePoint = useCallback(
    (clientX, clientY) => {
      const rect = containerRef.current.getBoundingClientRect()
      const bx = clamp((clientX - rect.left) / rect.width, 0, 1)
      const by = clamp((clientY - rect.top) / rect.height, 0, 1)
      return boxToImagePoint(bx, by, imageAspect)
    },
    [imageAspect],
  )

  const handlePointerMove = useCallback(
    (e) => {
      const drag = dragRef.current
      if (!drag) return
      const { x, y } = clientToImagePoint(e.clientX, e.clientY)

      if (drag.mode === 'move') {
        const dx = x - drag.startPoint.x
        const dy = y - drag.startPoint.y
        const newX = clamp(drag.startRect.x + dx, 0, 1 - drag.startRect.width)
        const newY = clamp(drag.startRect.y + dy, 0, 1 - drag.startRect.height)
        onCropRectChange({ ...drag.startRect, x: newX, y: newY })
        return
      }

      // 모서리 리사이즈 — 반대쪽 모서리(fixedCorner)는 그대로 두고, 드래그 중인 모서리
      // 좌표(x, y)와의 사각형을 다시 계산한다. 커서가 반대쪽 모서리를 넘어가도(뒤집혀도)
      // min/max로 정리되므로 사각형 자체는 항상 정상적인 형태를 유지한다.
      const { x: fixedX, y: fixedY } = drag.fixedCorner
      let cx = x
      if (Math.abs(cx - fixedX) < MIN_CROP_SIZE) cx = cx < fixedX ? fixedX - MIN_CROP_SIZE : fixedX + MIN_CROP_SIZE
      let cy = y
      if (Math.abs(cy - fixedY) < MIN_CROP_SIZE) cy = cy < fixedY ? fixedY - MIN_CROP_SIZE : fixedY + MIN_CROP_SIZE
      cx = clamp(cx, 0, 1)
      cy = clamp(cy, 0, 1)

      const minX = Math.min(fixedX, cx)
      const maxX = Math.max(fixedX, cx)
      const minY = Math.min(fixedY, cy)
      const maxY = Math.max(fixedY, cy)
      onCropRectChange({ x: minX, y: minY, width: maxX - minX, height: maxY - minY })
    },
    [clientToImagePoint, onCropRectChange],
  )

  const stopDrag = useCallback(() => {
    dragRef.current = null
    window.removeEventListener('pointermove', handlePointerMove)
    window.removeEventListener('pointerup', stopDrag)
  }, [handlePointerMove])

  const startMove = useCallback(
    (e) => {
      e.preventDefault()
      dragRef.current = { mode: 'move', startRect: cropRect, startPoint: clientToImagePoint(e.clientX, e.clientY) }
      window.addEventListener('pointermove', handlePointerMove)
      window.addEventListener('pointerup', stopDrag)
    },
    [cropRect, clientToImagePoint, handlePointerMove, stopDrag],
  )

  const startResize = useCallback(
    (e, corner) => {
      e.preventDefault()
      e.stopPropagation()
      const opposite = {
        nw: { x: cropRect.x + cropRect.width, y: cropRect.y + cropRect.height },
        ne: { x: cropRect.x, y: cropRect.y + cropRect.height },
        sw: { x: cropRect.x + cropRect.width, y: cropRect.y },
        se: { x: cropRect.x, y: cropRect.y },
      }[corner]
      dragRef.current = { mode: corner, fixedCorner: opposite }
      window.addEventListener('pointermove', handlePointerMove)
      window.addEventListener('pointerup', stopDrag)
    },
    [cropRect, handlePointerMove, stopDrag],
  )

  const topLeft = imageToBoxPoint(cropRect.x, cropRect.y, imageAspect)
  const bottomRight = imageToBoxPoint(cropRect.x + cropRect.width, cropRect.y + cropRect.height, imageAspect)

  return (
    <div className="photo-crop" ref={containerRef}>
      <img src={photoUrl} alt={alt} className="photo-crop-img" draggable={false} />
      <div
        className="photo-crop-rect"
        style={{
          left: `${topLeft.x * 100}%`,
          top: `${topLeft.y * 100}%`,
          width: `${(bottomRight.x - topLeft.x) * 100}%`,
          height: `${(bottomRight.y - topLeft.y) * 100}%`,
        }}
        onPointerDown={startMove}
      >
        {CORNERS.map((corner) => (
          <span
            key={corner}
            className={`photo-crop-handle photo-crop-handle-${corner}`}
            onPointerDown={(e) => startResize(e, corner)}
          />
        ))}
      </div>
      <div className="photo-crop-actions">
        <button type="button" className="squat-btn squat-btn-outline" onClick={onSkip}>
          건너뛰기
        </button>
        <button type="button" className="squat-btn squat-btn-primary" onClick={onApply}>
          자르기 적용
        </button>
      </div>
    </div>
  )
}

export default PhotoCropOverlay

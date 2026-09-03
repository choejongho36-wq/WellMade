/**
 * 사진 코칭 페이지 헤더의 운동 선택 드롭다운 — 지금은 스쿼트 하나뿐이지만(2026-09-02 시안),
 * 나중에 운동이 늘어날 걸 대비해 목록/선택 구조로 만들어뒀다. 바깥을 클릭하면 닫힌다.
 */

import { useEffect, useRef, useState } from 'react'

const EXERCISES = [{ id: 'squat', label: '스쿼트' }]

function ExerciseSelectDropdown({ value = 'squat', onChange }) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef(null)

  useEffect(() => {
    if (!open) return
    const handleClick = (e) => {
      if (!rootRef.current?.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [open])

  const current = EXERCISES.find((ex) => ex.id === value) ?? EXERCISES[0]

  return (
    <div className="exercise-dropdown" ref={rootRef}>
      <button
        type="button"
        className="exercise-dropdown-trigger"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span className="exercise-dropdown-dot" aria-hidden="true">●</span>
        {current.label}
        <span className="exercise-dropdown-arrow" aria-hidden="true">{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <ul className="exercise-dropdown-menu" role="listbox">
          {EXERCISES.map((ex) => (
            <li key={ex.id}>
              <button
                type="button"
                role="option"
                aria-selected={ex.id === value}
                className="exercise-dropdown-item"
                onClick={() => {
                  onChange?.(ex.id)
                  setOpen(false)
                }}
              >
                {ex.label}
                {ex.id === value && <span className="exercise-dropdown-check">✓</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default ExerciseSelectDropdown

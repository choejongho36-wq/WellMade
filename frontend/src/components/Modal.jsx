import { useEffect, useRef } from 'react'

/**
 * 공용 모달 껍데기. × 버튼 / Esc 로 닫히고, 열려 있는 동안 포커스를 안에 가둔다.
 *
 * 배경(바깥) 클릭으로는 기본적으로 닫히지 않는다 - 실수로 바깥을 눌러 입력 중이던 내용을
 * 잃는 걸 막기 위함. 입력이 없는 안내성 모달(운동방법 모달 등)은 closeOnBackdropClick로
 * 옵트인할 수 있다.
 *
 * 키 이벤트를 document가 아니라 모달 엘리먼트에서 받는 이유: 모달이 겹쳐 뜰 때
 * (기록 모달 위에 에러 모달) 포커스를 가진 맨 위 모달에서만 Esc가 처리되게 하려고.
 *
 * @param onClose  닫기 요청 - 닫으면 안 되는 상황(저장 중 등)이면 이 함수 안에서 무시하면 됨
 * @param className  .modal 에 덧붙일 클래스 (폭/정렬 등 개별 스타일)
 * @param closeOnBackdropClick  true면 모달 바깥 여백을 눌러도 닫힌다 (기본 false, 기존 동작 유지)
 */
function Modal({ onClose, className = '', closeOnBackdropClick = false, children }) {
  const dialogRef = useRef(null)
  // onClose가 매 렌더 새 함수라 effect 의존성에 넣으면 리스너/포커스가 계속 재설정된다
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose

  useEffect(() => {
    const previouslyFocused = document.activeElement
    dialogRef.current?.focus()
    return () => previouslyFocused?.focus?.()
  }, [])

  const handleKeyDown = (e) => {
    if (e.key === 'Escape') {
      onCloseRef.current()
      return
    }
    if (e.key !== 'Tab') return

    const focusables = dialogRef.current.querySelectorAll(
      'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    )
    if (focusables.length === 0) return

    const first = focusables[0]
    const last = focusables[focusables.length - 1]
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault()
      last.focus()
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault()
      first.focus()
    }
  }

  return (
    <div
      className="modal-backdrop"
      onClick={closeOnBackdropClick ? () => onCloseRef.current() : undefined}
    >
      <div
        className={`modal ${className}`.trim()}
        ref={dialogRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={handleKeyDown}
      >
        <button className="modal-close" onClick={() => onCloseRef.current()} aria-label="닫기">×</button>
        {children}
      </div>
    </div>
  )
}

export default Modal

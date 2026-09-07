/**
 * 전체 화면 대기화면 — 검은 배경 + 가운데 빨간 원형 스피너.
 * lazy(...)로 분리한 페이지 번들을 불러오는 동안 Suspense fallback으로 쓴다
 * (main.jsx 참고. 기존엔 fallback={null}이라 로딩 중 흰 화면만 보였음).
 */
import './LoadingScreen.css'

function LoadingScreen() {
  return (
    <div className="loading-screen" role="status" aria-live="polite" aria-label="로딩 중">
      <span className="loading-spinner" />
    </div>
  )
}

export default LoadingScreen

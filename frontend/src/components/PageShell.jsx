import './PageShell.css'
import { useAuth } from '../lib/auth.js'
import SiteNav from './SiteNav.jsx'

/**
 * @param bleed  true면 오른쪽 페이지 여백과 콘텐츠 안쪽 여백을 없애, 콘텐츠가 화면 끝까지
 *               꽉 차게 한다(운동 선택 화면처럼 콘텐츠 전체가 사진 한 장인 페이지용).
 *               왼쪽 네비와 빨간 세로 구분선은 그대로 유지된다. 기본값은 기존 동작.
 */
function PageShell({ children, bleed = false }) {
  const { user, handleLogout } = useAuth()

  return (
    <div className={bleed ? 'page-shell page-shell-bleed' : 'page-shell'}>
      <div className="page-shell-nav">
        <SiteNav user={user} onLogout={handleLogout} />
      </div>
      <div className="page-shell-content">
        {children}
      </div>
    </div>
  )
}

export default PageShell

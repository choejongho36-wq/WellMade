import { useAuth, SOCIAL_PROVIDERS, API_BASE } from '../lib/auth.js'
import './SiteNav.css'

/**
 * 토큰(1시간)이 만료되면 authFetch가 401을 받고 조용히 로그아웃시킨다. 그것만으로는
 * 화면이 갑자기 비로그인 상태로 바뀐 이유를 알 수 없어서, 만료된 그 순간 한 번 알려준다.
 */
function SessionExpiredModal() {
  const { sessionExpired, dismissSessionExpired } = useAuth()

  if (!sessionExpired) return null

  return (
    <div className="modal-backdrop">
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={dismissSessionExpired} aria-label="닫기">×</button>
        <div className="modal-title">로그인이 만료됐어요</div>
        <div className="modal-sub">
          보안을 위해 일정 시간이 지나면 자동으로 로그아웃돼요.
          다시 로그인하면 이어서 사용할 수 있어요.
        </div>
        <div className="nav-social">
          {SOCIAL_PROVIDERS.map((p) => (
            <a
              key={p.id}
              className="social-btn"
              style={{ background: p.bg, color: p.color }}
              href={`${API_BASE}/oauth2/authorization/${p.id}`}
            >
              <img src={p.icon} alt="" />
              {p.label}
            </a>
          ))}
        </div>
      </div>
    </div>
  )
}

export default SessionExpiredModal

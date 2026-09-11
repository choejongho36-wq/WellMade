import { Navigate, NavLink, Outlet } from 'react-router-dom'
import { useAdminAuth } from '../lib/adminAuth.js'
import './AdminLayout.css'

// 관리자 화면 공통 뼈대(사이드바 + 로그아웃) + 라우트 가드. 여기서 막는 건 화면단 UX일 뿐,
// 실제 권한 검사는 API 호출마다 백엔드(ROLE_ADMIN)가 다시 한다 — 이 가드를 우회해도 API가
// 거부한다.
export default function AdminLayout() {
  const { admin, logout } = useAdminAuth()

  if (admin === undefined) {
    return <div className="admin-loading">확인 중...</div>
  }
  if (admin === null) {
    return <Navigate to="/admin/login" replace />
  }

  return (
    <div className="admin-shell">
      <aside className="admin-sidebar">
        <div className="admin-brand">WellMade<span>관리자</span></div>
        <nav>
          <NavLink to="/admin" end>대시보드</NavLink>
          <NavLink to="/admin/reports">신고 관리</NavLink>
          <NavLink to="/admin/inquiries">1:1 문의</NavLink>
          <NavLink to="/admin/faqs">FAQ 관리</NavLink>
          <NavLink to="/admin/notices">공지사항 관리</NavLink>
        </nav>
        <button type="button" className="admin-logout" onClick={logout}>로그아웃</button>
      </aside>
      <main className="admin-main">
        <Outlet />
      </main>
    </div>
  )
}

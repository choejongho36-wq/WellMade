import { StrictMode, Suspense, lazy } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route, Outlet, useLocation } from 'react-router-dom'
import './index.css'
import { AuthProvider, useAuth } from './lib/auth.js'
import { AdminAuthProvider } from './lib/adminAuth.js'
import ChatWidget from './components/ChatWidget.jsx'
import ErrorBoundary from './components/ErrorBoundary.jsx'
import LoadingScreen from './components/LoadingScreen.jsx'
import SessionExpiredModal from './components/SessionExpiredModal.jsx'
import MainPage from './pages/MainPage.jsx'
import MyPage from './pages/MyPage.jsx'
import DietPage from './pages/DietPage.jsx'
import NotFoundPage from './pages/NotFoundPage.jsx'

// 자세 측정(스쿼트 코칭) 흐름 — 모드 선택 허브 + 사진 코칭 + 실시간 코칭. 셋 다
// MediaPipe 계산 코드가 무거워 첫 화면 번들에서 분리한다.
const SquatModeSelectPage = lazy(() => import('./pages/SquatModeSelectPage.jsx'))
const PhotoCoachingPage = lazy(() => import('./pages/PhotoCoachingPage.jsx'))
const SquatCoachingPage = lazy(() => import('./pages/SquatCoachingPage.jsx'))
// 운동 기록 페이지(2026-09-09 추가)는 카메라/MediaPipe 코드가 없는 가벼운 페이지라 위
// 셋과 분리해서 따로 청크로 뺐다(ExerciseHistoryPage.jsx 파일 상단 주석 참고).
const ExerciseHistoryPage = lazy(() => import('./pages/ExerciseHistoryPage.jsx'))
const PosturePage = lazy(() => import('./pages/PosturePage.jsx'))

// 관리자 대시보드(2026-09-09, 백엔드 Thymeleaf 세션 로그인 -> 프론트 전환) — 일반 사용자용
// 번들에 섞이지 않게 별도 청크로 뺀다. 로그인은 httpOnly 쿠키 기반 admin 전용 JWT를 쓰고
// (lib/adminAuth.js 참고), 일반 회원 AuthProvider와는 완전히 분리된 인증 상태를 쓴다.
const AdminLoginPage = lazy(() => import('./pages/AdminLoginPage.jsx'))
const AdminLayout = lazy(() => import('./components/AdminLayout.jsx'))
const AdminDashboardPage = lazy(() => import('./pages/AdminDashboardPage.jsx'))
const AdminReportsPage = lazy(() => import('./pages/AdminReportsPage.jsx'))
const AdminReportDetailPage = lazy(() => import('./pages/AdminReportDetailPage.jsx'))

function AppRoutes() {
  const { user, profile, sendChat, getChatHistory, clearChatHistory, getNutrientAdvice, sendChatMenu } = useAuth()
  // 관리자 화면(/admin/**)에는 일반 회원용 고객센터 챗위젯/세션만료 모달을 띄우지 않는다 —
  // 관리자는 별도 인증 상태(adminAuth.js)를 쓰고 있어 이 둘은 그 화면에서 아무 의미가 없다.
  const isAdminRoute = useLocation().pathname.startsWith('/admin')

  return (
    <>
      <Suspense fallback={<LoadingScreen />}>
        <Routes>
          <Route path="/" element={<MainPage />} />
          <Route path="/mypage" element={<MyPage />} />
          <Route path="/mealplan" element={<DietPage />} />
          <Route path="/exercises" element={<SquatModeSelectPage />} />
          <Route path="/exercises/photo" element={<PhotoCoachingPage />} />
          <Route path="/exercises/live" element={<SquatCoachingPage />} />
          <Route path="/exercises-history" element={<ExerciseHistoryPage />} />
          <Route path="/posture" element={<PosturePage />} />
          <Route path="/oauth/redirect" element={<MainPage />} />

          <Route path="/admin" element={<AdminAuthProvider><Outlet /></AdminAuthProvider>}>
            <Route path="login" element={<AdminLoginPage />} />
            <Route element={<AdminLayout />}>
              <Route index element={<AdminDashboardPage />} />
              <Route path="reports" element={<AdminReportsPage />} />
              <Route path="reports/:id" element={<AdminReportDetailPage />} />
            </Route>
          </Route>

          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </Suspense>

      {!isAdminRoute && <SessionExpiredModal />}
      {!isAdminRoute && (
        <ChatWidget loggedIn={Boolean(user)} sendChat={sendChat} getChatHistory={getChatHistory} clearChatHistory={clearChatHistory} getNutrientAdvice={getNutrientAdvice} sendChatMenu={sendChatMenu} userName={profile?.name} />
      )}
    </>
  )
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <ErrorBoundary>
          <AppRoutes />
        </ErrorBoundary>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
)

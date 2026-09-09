import { StrictMode, Suspense, lazy } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import './index.css'
import { AuthProvider, useAuth } from './lib/auth.js'
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

function AppRoutes() {
  const { user, profile, sendChat, getChatHistory, clearChatHistory, getNutrientAdvice, sendChatMenu } = useAuth()

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
          <Route path="/oauth/redirect" element={<MainPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </Suspense>

      <SessionExpiredModal />
      <ChatWidget loggedIn={Boolean(user)} sendChat={sendChat} getChatHistory={getChatHistory} clearChatHistory={clearChatHistory} getNutrientAdvice={getNutrientAdvice} sendChatMenu={sendChatMenu} userName={profile?.name} />
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

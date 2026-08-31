import { StrictMode, Suspense, lazy } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import './index.css'
import { AuthProvider, useAuth } from './lib/auth.js'
import ChatWidget from './components/ChatWidget.jsx'
import ErrorBoundary from './components/ErrorBoundary.jsx'
import MainPage from './pages/MainPage.jsx'
import MyPage from './pages/MyPage.jsx'
import DietPage from './pages/DietPage.jsx'
import NotFoundPage from './pages/NotFoundPage.jsx'

// 1,700줄 + MediaPipe 계산 코드라 첫 화면 번들에 같이 넣을 이유가 없다
const MlTestPage = lazy(() => import('./pages/MlTestPage.jsx'))

function AppRoutes() {
  const { user, profile, sendChat, getChatHistory, clearChatHistory, getNutrientAdvice } = useAuth()

  return (
    <>
      <Suspense fallback={null}>
        <Routes>
          <Route path="/" element={<MainPage />} />
          <Route path="/mypage" element={<MyPage />} />
          <Route path="/mealplan" element={<DietPage />} />
          <Route path="/ml-test" element={<MlTestPage />} />
          <Route path="/oauth/redirect" element={<MainPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </Suspense>

      <ChatWidget loggedIn={Boolean(user)} sendChat={sendChat} getChatHistory={getChatHistory} clearChatHistory={clearChatHistory} getNutrientAdvice={getNutrientAdvice} userName={profile?.name} />
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

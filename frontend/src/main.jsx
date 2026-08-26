import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import './index.css'
import { useAuth } from './lib/auth.js'
import ChatWidget from './components/ChatWidget.jsx'
import ErrorBoundary from './components/ErrorBoundary.jsx'
import MainPage from './pages/MainPage.jsx'
import MyPage from './pages/MyPage.jsx'
import PosturePage from './pages/PosturePage.jsx'
import MlTestPage from './pages/MlTestPage.jsx'
import DietPage from './pages/DietPage.jsx'
import NotFoundPage from './pages/NotFoundPage.jsx'

function AppRoutes() {
  const { profile, sendChat, getChatHistory, getNutrientAdvice } = useAuth()

  return (
    <>
      <Routes>
        <Route path="/" element={<MainPage />} />
        <Route path="/mypage" element={<MyPage />} />
        <Route path="/posture" element={<PosturePage />} />
        <Route path="/mealplan" element={<DietPage />} />
        <Route path="/ml-test" element={<MlTestPage />} />
        <Route path="/oauth/redirect" element={<MainPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>

      <ChatWidget sendChat={sendChat} getChatHistory={getChatHistory} getNutrientAdvice={getNutrientAdvice} userName={profile?.name} />
    </>
  )
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <ErrorBoundary>
        <AppRoutes />
      </ErrorBoundary>
    </BrowserRouter>
  </StrictMode>,
)

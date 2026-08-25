import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import './index.css'
import { useAuth } from './lib/auth.js'
import ChatWidget from './components/ChatWidget.jsx'
import MainPage from './pages/MainPage.jsx'
import MyPage from './pages/MyPage.jsx'
import PosturePage from './pages/PosturePage.jsx'
import MlTestPage from './pages/MlTestPage.jsx'
import DietPage from './pages/DietPage.jsx'

function AppRoutes() {
  const { profile, sendChat, getNutrientAdvice } = useAuth()

  return (
    <>
      <Routes>
        <Route path="/" element={<MainPage />} />
        <Route path="/mypage" element={<MyPage />} />
        <Route path="/posture" element={<PosturePage />} />
        <Route path="/mealplan" element={<DietPage />} />
        <Route path="/ml-test" element={<MlTestPage />} />
        <Route path="/oauth/redirect" element={<MainPage />} />
      </Routes>

      <ChatWidget sendChat={sendChat} getNutrientAdvice={getNutrientAdvice} userName={profile?.name} />
    </>
  )
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  </StrictMode>,
)

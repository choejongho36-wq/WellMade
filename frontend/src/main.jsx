import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import './index.css'
import MainPage from './MainPage.jsx'
import MyPage from './MyPage.jsx'
import PosturePage from './PosturePage.jsx'
import MlTestPage from './MlTestPage.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<MainPage />} />
        <Route path="/mypage" element={<MyPage />} />
        <Route path="/posture" element={<PosturePage />} />
        <Route path="/ml-test" element={<MlTestPage />} />
        <Route path="/oauth/redirect" element={<MainPage />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>,
)

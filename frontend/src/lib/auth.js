import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import iconGoogle from '../assets/icon-google.png'
import iconKakao from '../assets/icon-kakao.png'
import iconNaver from '../assets/icon-naver.png'

export const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8080'
export const TOKEN_KEY = 'accessToken'
const USER_CACHE_KEY = 'cachedUser'

function readCachedUser() {
  try {
    const cached = sessionStorage.getItem(USER_CACHE_KEY)
    return cached ? JSON.parse(cached) : null
  } catch {
    return null
  }
}
export const SOCIAL_PROVIDERS = [
  { id: 'google', label: '구글 로그인', icon: iconGoogle, bg: '#f2f2f2', color: '#111' },
  { id: 'kakao', label: '카카오 로그인', icon: iconKakao, bg: '#fee500', color: '#191919' },
  { id: 'naver', label: '네이버 로그인', icon: iconNaver, bg: '#05ac4f', color: '#fff' },
]

export const NAV_ITEMS = [
  { label: '마이페이지', path: '/mypage' },
  { label: '자세 측정', path: '/posture' },
  { label: '식단 기록', path: '/mealplan' },
  { label: '운동 추천' },
]

export function useAuth() {
  const [user, setUser] = useState(readCachedUser)
  const [profile, setProfile] = useState(null)
  const [inbody, setInbody] = useState(null)
  const codeExchanged = useRef(false)
  const navigate = useNavigate()

  useEffect(() => {
    const fetchMe = (token) => {
      const authHeader = { Authorization: `Bearer ${token}` }
      fetch(`${API_BASE}/api/users/me`, { headers: authHeader })
        .then((res) => {
          if (!res.ok) throw new Error('unauthorized')
          return res.json()
        })
        .then((data) => {
          setUser(data)
          sessionStorage.setItem(USER_CACHE_KEY, JSON.stringify(data))
        })
        .catch(() => {
          localStorage.removeItem(TOKEN_KEY)
          sessionStorage.removeItem(USER_CACHE_KEY)
          setUser(null)
        })

      fetch(`${API_BASE}/api/users/me/profile`, { headers: authHeader })
        .then((res) => (res.ok ? res.json() : null))
        .then(setProfile)

      fetch(`${API_BASE}/api/users/me/inbody/latest`, { headers: authHeader })
        .then((res) => (res.status === 200 ? res.json() : null))
        .then(setInbody)
    }

    const code = new URLSearchParams(window.location.search).get('code')
    if (window.location.pathname === '/oauth/redirect' && code) {
      if (codeExchanged.current) return
      codeExchanged.current = true

      fetch(`${API_BASE}/api/auth/token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code }),
      })
        .then((res) => (res.ok ? res.json() : null))
        .then((data) => {
          if (!data) return
          localStorage.setItem(TOKEN_KEY, data.accessToken)
          navigate('/', { replace: true })
          fetchMe(data.accessToken)
        })
      return
    }

    const token = localStorage.getItem(TOKEN_KEY)
    if (token) fetchMe(token)
  }, [])

  const handleLogout = () => {
    localStorage.removeItem(TOKEN_KEY)
    sessionStorage.removeItem(USER_CACHE_KEY)
    setUser(null)
    setProfile(null)
    setInbody(null)
  }

  const deleteAccount = () => {
    const token = localStorage.getItem(TOKEN_KEY)
    if (!token) return Promise.reject(new Error('로그인이 필요합니다'))

    return fetch(`${API_BASE}/api/users/me`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${token}` },
    }).then((res) => {
      if (!res.ok) throw new Error('탈퇴에 실패했어요')
      handleLogout()
    })
  }

  const extractInbody = (file) => {
    const token = localStorage.getItem(TOKEN_KEY)
    if (!token) return Promise.reject(new Error('로그인이 필요합니다'))

    const formData = new FormData()
    formData.append('image', file)

    return fetch(`${API_BASE}/api/users/me/inbody/extract`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: formData,
    }).then((res) => {
      if (!res.ok) throw new Error('인바디 인식 실패')
      return res.json()
    })
  }

  const confirmInbody = (values) => {
    const token = localStorage.getItem(TOKEN_KEY)
    if (!token) return Promise.reject(new Error('로그인이 필요합니다'))

    return fetch(`${API_BASE}/api/users/me/inbody`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(values),
    }).then((res) => {
      if (!res.ok) throw new Error('인바디 등록 실패')
      return res.json()
    }).then((data) => {
      setInbody(data)
      return data
    })
  }

  const updateGoal = (goal) => {
    const token = localStorage.getItem(TOKEN_KEY)
    if (!token) return Promise.reject(new Error('로그인이 필요합니다'))

    return fetch(`${API_BASE}/api/users/me/profile`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        name: profile?.name,
        profileImageUrl: profile?.profileImageUrl,
        goal,
      }),
    }).then((res) => {
      if (res.ok) setProfile((prev) => ({ ...prev, goal }))
      return res.ok
    })
  }

  const updateName = (name) => {
    const token = localStorage.getItem(TOKEN_KEY)
    if (!token) return Promise.reject(new Error('로그인이 필요합니다'))

    return fetch(`${API_BASE}/api/users/me/profile`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        name,
        profileImageUrl: profile?.profileImageUrl,
        goal: profile?.goal,
      }),
    }).then((res) => {
      if (!res.ok) {
        return res.text().then((message) => {
          throw new Error(message || '닉네임 변경에 실패했어요')
        })
      }
      setProfile((prev) => ({ ...prev, name }))
    })
  }

  // 대화 이력을 이제 서버가 갖고 있어서(9번 패치), 매번 전체 배열이 아니라 새 메시지 하나만 보내면 됨
  const sendChat = (message) => {
    const token = localStorage.getItem(TOKEN_KEY)
    if (!token) return Promise.reject(new Error('로그인이 필요합니다'))

    return fetch(`${API_BASE}/api/users/me/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ message }),
    }).then((res) => {
      if (!res.ok) throw new Error('답변을 받지 못했어요')
      return res.json()
    }).then((data) => data.content)
  }

  const getChatHistory = () => {
    const token = localStorage.getItem(TOKEN_KEY)
    if (!token) return Promise.reject(new Error('로그인이 필요합니다'))

    return fetch(`${API_BASE}/api/users/me/chat/history`, {
      headers: { Authorization: `Bearer ${token}` },
    }).then((res) => {
      if (!res.ok) throw new Error('대화 이력을 불러오지 못했어요')
      return res.json()
    })
  }

  const getNutrientAdvice = () => {
    const token = localStorage.getItem(TOKEN_KEY)
    if (!token) return Promise.reject(new Error('로그인이 필요합니다'))

    return fetch(`${API_BASE}/api/users/me/chat/nutrient-advice`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    }).then((res) => {
      if (!res.ok) throw new Error('분석을 받지 못했어요')
      return res.json()
    }).then((data) => data.content)
  }

  const logMeal = (message, mealType) => {
    const token = localStorage.getItem(TOKEN_KEY)
    if (!token) return Promise.reject(new Error('로그인이 필요합니다'))

    return fetch(`${API_BASE}/api/diet/meals`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ message, mealType: mealType || null }),
    }).then((res) => {
      if (!res.ok) throw new Error('식단 기록에 실패했어요')
      return res.json()
    })
  }

  const getTodayMeals = (date) => {
    const token = localStorage.getItem(TOKEN_KEY)
    if (!token) return Promise.reject(new Error('로그인이 필요합니다'))

    const query = date ? `?date=${date}` : ''
    return fetch(`${API_BASE}/api/diet/meals/today${query}`, {
      headers: { Authorization: `Bearer ${token}` },
    }).then((res) => {
      if (!res.ok) throw new Error('식단 기록을 불러오지 못했어요')
      return res.json()
    })
  }

  const getTodayTotal = (date) => {
    const token = localStorage.getItem(TOKEN_KEY)
    if (!token) return Promise.reject(new Error('로그인이 필요합니다'))

    const query = date ? `?date=${date}` : ''
    return fetch(`${API_BASE}/api/diet/meals/today/total${query}`, {
      headers: { Authorization: `Bearer ${token}` },
    }).then((res) => {
      if (!res.ok) throw new Error('합계를 불러오지 못했어요')
      return res.json()
    })
  }

  // 달력 칸에 날짜별 칼로리를 표시하기 위한 월 단위 합계. { "2026-08-05": 1850, ... } 형태
  const getMonthCalories = (year, month) => {
    const token = localStorage.getItem(TOKEN_KEY)
    if (!token) return Promise.reject(new Error('로그인이 필요합니다'))

    return fetch(`${API_BASE}/api/diet/meals/month?year=${year}&month=${month}`, {
      headers: { Authorization: `Bearer ${token}` },
    }).then((res) => {
      if (!res.ok) throw new Error('월별 기록을 불러오지 못했어요')
      return res.json()
    })
  }

  // 목표+인바디가 아직 없으면 서버가 204(본문 없음)를 주므로 null로 처리
  const getNutrientTarget = () => {
    const token = localStorage.getItem(TOKEN_KEY)
    if (!token) return Promise.reject(new Error('로그인이 필요합니다'))

    return fetch(`${API_BASE}/api/diet/meals/target`, {
      headers: { Authorization: `Bearer ${token}` },
    }).then((res) => (res.status === 200 ? res.json() : null))
  }

  const updateNutrientTarget = ({ kcal, proteinG, carbsG, fatG }) => {
    const token = localStorage.getItem(TOKEN_KEY)
    if (!token) return Promise.reject(new Error('로그인이 필요합니다'))

    return fetch(`${API_BASE}/api/diet/meals/target`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ kcal, proteinG, carbsG, fatG }),
    }).then((res) => {
      if (!res.ok) throw new Error('목표 저장에 실패했어요')
      return getNutrientTarget()
    })
  }

  const resetNutrientTarget = () => {
    const token = localStorage.getItem(TOKEN_KEY)
    if (!token) return Promise.reject(new Error('로그인이 필요합니다'))

    return fetch(`${API_BASE}/api/diet/meals/target`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${token}` },
    }).then((res) => {
      if (!res.ok) throw new Error('초기화에 실패했어요')
      return getNutrientTarget()
    })
  }

  const updateMeal = (id, { mealType, menuName, kcal }) => {
    const token = localStorage.getItem(TOKEN_KEY)
    if (!token) return Promise.reject(new Error('로그인이 필요합니다'))

    return fetch(`${API_BASE}/api/diet/meals/${id}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ mealType, menuName, kcal }),
    }).then((res) => {
      if (!res.ok) throw new Error('수정에 실패했어요')
    })
  }

  const updateMealItemAmount = (mealId, itemIndex, amountG) => {
    const token = localStorage.getItem(TOKEN_KEY)
    if (!token) return Promise.reject(new Error('로그인이 필요합니다'))

    return fetch(`${API_BASE}/api/diet/meals/${mealId}/items/${itemIndex}`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ amountG }),
    }).then((res) => {
      if (!res.ok) {
        return res.text().then((message) => {
          throw new Error(message || '그램 수 수정에 실패했어요')
        })
      }
      return res.json()
    })
  }

  const deleteMeal = (id) => {
    const token = localStorage.getItem(TOKEN_KEY)
    if (!token) return Promise.reject(new Error('로그인이 필요합니다'))

    return fetch(`${API_BASE}/api/diet/meals/${id}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${token}` },
    }).then((res) => {
      if (!res.ok) throw new Error('삭제에 실패했어요')
    })
  }

  return {
    user, profile, inbody, handleLogout, deleteAccount, updateGoal, updateName, extractInbody, confirmInbody,
    logMeal, getTodayMeals, getTodayTotal, getMonthCalories, getNutrientTarget, updateNutrientTarget, resetNutrientTarget,
    updateMeal, updateMealItemAmount, deleteMeal,
    sendChat, getChatHistory, getNutrientAdvice,
  }
}

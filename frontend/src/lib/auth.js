import { createContext, createElement, useContext, useEffect, useRef, useState } from 'react'
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
  { label: '자세 측정', path: '/ml-test' },
  { label: '식단 기록', path: '/mealplan' },
  { label: '고객센터' },
]

// 로그인 상태와 API 호출 함수를 트리 전체가 공유한다. 예전에는 useAuth()를 호출하는
// 컴포넌트마다 별도 state와 별도 초기 fetch가 생겨서 (1) 페이지 하나에 /api/users/me 등이
// 여러 번 호출되고 (2) 한쪽에서 닉네임을 바꿔도 다른 쪽 화면은 옛 값을 들고 있었으며
// (3) /oauth/redirect 에서 두 인스턴스가 같은 code를 동시에 교환하려다 한쪽이 실패했다.
const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  return createElement(AuthContext.Provider, { value: useAuthState() }, children)
}

export function useAuth() {
  return useContext(AuthContext)
}

function useAuthState() {
  const [user, setUser] = useState(readCachedUser)
  const [profile, setProfile] = useState(null)
  const [inbody, setInbody] = useState(null)
  const [sessionExpired, setSessionExpired] = useState(false)
  const codeExchanged = useRef(false)
  const navigate = useNavigate()

  const handleLogout = () => {
    localStorage.removeItem(TOKEN_KEY)
    sessionStorage.removeItem(USER_CACHE_KEY)
    setUser(null)
    setProfile(null)
    setInbody(null)
  }

  /**
   * 토큰을 붙여 API를 호출하고 Response를 그대로 돌려준다(본문 파싱은 호출부 몫 -
   * 204나 SSE 스트림처럼 json()을 못 쓰는 응답이 있어서).
   *
   * 토큰이 1시간이면 만료되는데, 예전에는 만료 후에도 각 함수가 "식단 기록에 실패했어요"
   * 같은 엉뚱한 메시지만 던지고 로그인 상태는 그대로 남아 있었다. 401을 여기서 한 번에
   * 처리해서 로그아웃시키고 만료된 것을 알린다.
   */
  const authFetch = async (path, options = {}) => {
    const token = localStorage.getItem(TOKEN_KEY)
    if (!token) throw new Error('로그인이 필요합니다')

    const headers = { ...options.headers, Authorization: `Bearer ${token}` }
    // FormData는 브라우저가 boundary까지 담아 Content-Type을 직접 붙여야 해서 건드리지 않는다
    if (options.body && !(options.body instanceof FormData) && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json'
    }

    const res = await fetch(`${API_BASE}${path}`, { ...options, headers })
    if (res.status === 401) {
      handleLogout()
      setSessionExpired(true)
      throw new Error('로그인이 만료됐어요. 다시 로그인해주세요')
    }
    return res
  }

  // 응답 본문이 있는 표준 케이스 - 실패하면 주어진 메시지로 예외를 던진다
  const authJson = async (path, options, failMessage) => {
    const res = await authFetch(path, options)
    if (!res.ok) throw new Error(failMessage)
    return res.json()
  }

  // 서버가 실패 사유를 본문에 담아주는 케이스(닉네임 중복 등)
  const authJsonWithServerError = async (path, options, failMessage) => {
    const res = await authFetch(path, options)
    if (!res.ok) throw new Error((await res.text()) || failMessage)
    return res.json()
  }

  useEffect(() => {
    const loadMe = () => {
      authJson('/api/users/me', {}, 'unauthorized')
        .then((data) => {
          setUser(data)
          sessionStorage.setItem(USER_CACHE_KEY, JSON.stringify(data))
        })
        .catch(handleLogout)

      authFetch('/api/users/me/profile')
        .then((res) => (res.ok ? res.json() : null))
        .then(setProfile)
        .catch(() => setProfile(null))

      authFetch('/api/users/me/inbody/latest')
        .then((res) => (res.status === 200 ? res.json() : null))
        .then(setInbody)
        .catch(() => setInbody(null))
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
          loadMe()
        })
      return
    }

    if (localStorage.getItem(TOKEN_KEY)) loadMe()
  }, [])

  const deleteAccount = () =>
    authFetch('/api/users/me', { method: 'DELETE' }).then((res) => {
      if (!res.ok) throw new Error('탈퇴에 실패했어요')
      handleLogout()
    })

  const extractInbody = (file) => {
    const formData = new FormData()
    formData.append('image', file)
    return authJson('/api/users/me/inbody/extract', { method: 'POST', body: formData }, '인바디 인식 실패')
  }

  const confirmInbody = (values) =>
    authJson('/api/users/me/inbody', { method: 'POST', body: JSON.stringify(values) }, '인바디 등록 실패')
      .then((data) => {
        setInbody(data)
        return data
      })

  // 잘못 등록한 기록 삭제. 지운 게 최신 기록이면 화면의 인바디도 이전 기록으로 되돌아가야 해서
  // 삭제 후 latest를 다시 읽어온다 (이력 재조회는 MyPage가 inbody 변화를 보고 알아서 함)
  const deleteInbody = (id) =>
    authFetch(`/api/users/me/inbody/${id}`, { method: 'DELETE' }).then((res) => {
      if (!res.ok) throw new Error('삭제에 실패했어요')
      return authFetch('/api/users/me/inbody/latest')
        .then((r) => (r.status === 200 ? r.json() : null))
        .then(setInbody)
    })

  const getInbodyHistory = () =>
    authJson('/api/users/me/inbody/history', {}, '인바디 이력을 불러오지 못했어요')

  // 성별/키/출생연도. 목표 칼로리·기초대사량이 이 값으로 계산되므로 저장 후 프로필 상태도 같이 갱신함
  const updateBody = ({ gender, heightCm, birthYear }) =>
    authFetch('/api/users/me/profile/body', {
      method: 'PUT',
      body: JSON.stringify({ gender, heightCm, birthYear }),
    }).then((res) => {
      if (!res.ok) throw new Error('신체 정보 저장에 실패했어요')
      setProfile((prev) => ({ ...prev, gender, heightCm, birthYear }))
    })

  const updateGoal = (goal) =>
    authFetch('/api/users/me/profile', {
      method: 'PUT',
      body: JSON.stringify({ name: profile?.name, profileImageUrl: profile?.profileImageUrl, goal }),
    }).then((res) => {
      if (res.ok) setProfile((prev) => ({ ...prev, goal }))
      return res.ok
    })

  const updateName = (name) =>
    authFetch('/api/users/me/profile', {
      method: 'PUT',
      body: JSON.stringify({ name, profileImageUrl: profile?.profileImageUrl, goal: profile?.goal }),
    }).then(async (res) => {
      if (!res.ok) throw new Error((await res.text()) || '닉네임 변경에 실패했어요')
      setProfile((prev) => ({ ...prev, name }))
    })

  // 대화 이력을 이제 서버가 갖고 있어서(9번 패치), 매번 전체 배열이 아니라 새 메시지 하나만 보내면 됨.
  // 응답은 SSE 스트림 - 토큰이 올 때마다 onDelta(누적문자열)를 호출하고, 최종 전체 문자열을 반환함.
  const sendChat = async (message, onDelta) => {
    const res = await authFetch('/api/users/me/chat', {
      method: 'POST',
      body: JSON.stringify({ message }),
    })
    if (!res.ok || !res.body) throw new Error('답변을 받지 못했어요')

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let full = ''

    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      // SSE는 이벤트마다 빈 줄로 구분. 마지막 조각은 아직 안 끝났을 수 있으니 buffer에 남겨둠
      const events = buffer.split('\n\n')
      buffer = events.pop() ?? ''

      for (const evt of events) {
        const data = evt
          .split('\n')
          .filter((l) => l.startsWith('data:'))
          .map((l) => l.slice(5).trimStart())
          .join('')
        if (!data) continue

        // 청크 하나가 깨져도 스트림 전체를 죽이지는 않는다
        let parsed
        try {
          parsed = JSON.parse(data)
        } catch {
          continue
        }
        if (parsed.error) throw new Error(parsed.error)
        if (parsed.t) {
          full += parsed.t
          onDelta?.(full)
        }
      }
    }
    return full
  }

  const getChatHistory = () =>
    authJson('/api/users/me/chat/history', {}, '대화 이력을 불러오지 못했어요')

  const clearChatHistory = () =>
    authFetch('/api/users/me/chat/history', { method: 'DELETE' }).then((res) => {
      if (!res.ok) throw new Error('대화 기록을 지우지 못했어요')
    })

  const getNutrientAdvice = () =>
    authJson('/api/users/me/chat/nutrient-advice', { method: 'POST' }, '분석을 받지 못했어요')
      .then((data) => data.content)

  // date를 넘기면 그 날짜로 기록된다(깜빡한 지난 끼니 채워넣기). 생략하면 서버가 오늘로 처리
  const logMeal = (message, mealType, date) =>
    authJson('/api/diet/meals', {
      method: 'POST',
      body: JSON.stringify({ message, mealType: mealType || null, date: date || null }),
    }, '식단 기록에 실패했어요')

  // 표준 식품 DB에 없어서 자동 조회가 안 된 음식 - 사용자가 칼로리를 직접 적어 기록할 때
  const logManualMeal = (foodName, kcal, mealType, date) =>
    authJsonWithServerError('/api/diet/meals/manual', {
      method: 'POST',
      body: JSON.stringify({ foodName, kcal, mealType: mealType || null, date: date || null }),
    }, '직접 기록에 실패했어요')

  const getTodayMeals = (date) =>
    authJson(`/api/diet/meals/today${date ? `?date=${date}` : ''}`, {}, '식단 기록을 불러오지 못했어요')

  const getTodayTotal = (date) =>
    authJson(`/api/diet/meals/today/total${date ? `?date=${date}` : ''}`, {}, '합계를 불러오지 못했어요')

  // 달력 칸에 날짜별 칼로리를 표시하기 위한 월 단위 합계. { "2026-08-05": 1850, ... } 형태
  const getMonthCalories = (year, month) =>
    authJson(`/api/diet/meals/month?year=${year}&month=${month}`, {}, '월별 기록을 불러오지 못했어요')

  // 달력 칸에 공휴일을 표시하기 위한 월 단위 조회. { "2026-01-01": "신정", ... } 형태
  // (서버가 공공데이터포털 API로 조회 - 키 미설정이면 그냥 빈 객체가 옴)
  const getHolidays = (year, month) =>
    authJson(`/api/calendar/holidays?year=${year}&month=${month}`, {}, '공휴일 정보를 불러오지 못했어요')

  // 목표+인바디가 아직 없으면 서버가 204(본문 없음)를 주므로 null로 처리
  const getNutrientTarget = () =>
    authFetch('/api/diet/meals/target').then((res) => (res.status === 200 ? res.json() : null))

  const updateNutrientTarget = ({ kcal, proteinG, carbsG, fatG }) =>
    authFetch('/api/diet/meals/target', {
      method: 'PUT',
      body: JSON.stringify({ kcal, proteinG, carbsG, fatG }),
    }).then((res) => {
      if (!res.ok) throw new Error('목표 저장에 실패했어요')
      return getNutrientTarget()
    })

  const resetNutrientTarget = () =>
    authFetch('/api/diet/meals/target', { method: 'DELETE' }).then((res) => {
      if (!res.ok) throw new Error('초기화에 실패했어요')
      return getNutrientTarget()
    })

  const updateMeal = (id, { mealType, menuName, kcal }) =>
    authFetch(`/api/diet/meals/${id}`, {
      method: 'PUT',
      body: JSON.stringify({ mealType, menuName, kcal }),
    }).then(async (res) => {
      // 이름을 바꾸면 서버가 그 음식으로 다시 조회하는데, 못 찾으면 이유를 그대로 보여줌
      if (!res.ok) throw new Error((await res.text()) || '수정에 실패했어요')
    })

  const updateMealItemAmount = (mealId, itemIndex, amountG) =>
    authJsonWithServerError(`/api/diet/meals/${mealId}/items/${itemIndex}`, {
      method: 'PATCH',
      body: JSON.stringify({ amountG }),
    }, '그램 수 수정에 실패했어요')

  // 매칭이 불확실한(matchTier: FUZZY) 항목에 대해 사용자가 후보 중 하나를 직접 고를 때 씀.
  // 이 선택은 서버가 기억해뒀다가 다음에 같은 표현이 나오면 자동으로 적용됨
  const resolveMealItemMatch = (mealId, itemIndex, resolvedFoodName) =>
    authJsonWithServerError(`/api/diet/meals/${mealId}/items/${itemIndex}/match`, {
      method: 'PATCH',
      body: JSON.stringify({ resolvedFoodName }),
    }, '매칭 변경에 실패했어요')

  const deleteMeal = (id) =>
    authFetch(`/api/diet/meals/${id}`, { method: 'DELETE' }).then((res) => {
      if (!res.ok) throw new Error('삭제에 실패했어요')
    })

  return {
    user, profile, inbody, handleLogout,
    sessionExpired, dismissSessionExpired: () => setSessionExpired(false),
    deleteAccount, updateGoal, updateName, updateBody, extractInbody, confirmInbody, deleteInbody, getInbodyHistory,
    logMeal, getTodayMeals, getTodayTotal, getMonthCalories, getHolidays, getNutrientTarget, updateNutrientTarget, resetNutrientTarget,
    logManualMeal,
    updateMeal, updateMealItemAmount, resolveMealItemMatch, deleteMeal,
    sendChat, getChatHistory, clearChatHistory, getNutrientAdvice,
  }
}

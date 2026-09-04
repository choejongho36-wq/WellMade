import { createContext, createElement, useCallback, useContext, useEffect, useRef, useState } from 'react'
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
  { label: '자세 측정', path: '/squat' },
  { label: '캘린더', path: '/mealplan' },
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

  // 아래 API 함수들은 useEffect 안에서 불리는 게 많은데, 매 렌더 새로 만들어지면 의존성 배열에
  // 넣을 수가 없어서 exhaustive-deps를 끄고 쓰게 된다(그러면 진짜 빠뜨린 의존성도 같이 묻힌다).
  // 뿌리인 handleLogout/authFetch부터 고정해두면 그 위의 함수들도 같이 고정할 수 있다.
  const handleLogout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY)
    sessionStorage.removeItem(USER_CACHE_KEY)
    setUser(null)
    setProfile(null)
    setInbody(null)
  }, [])

  /**
   * 토큰을 붙여 API를 호출하고 Response를 그대로 돌려준다(본문 파싱은 호출부 몫 -
   * 204나 SSE 스트림처럼 json()을 못 쓰는 응답이 있어서).
   *
   * 토큰이 1시간이면 만료되는데, 예전에는 만료 후에도 각 함수가 "식단 기록에 실패했어요"
   * 같은 엉뚱한 메시지만 던지고 로그인 상태는 그대로 남아 있었다. 401을 여기서 한 번에
   * 처리해서 로그아웃시키고 만료된 것을 알린다.
   */
  const authFetch = useCallback(async (path, options = {}) => {
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
  }, [handleLogout])

  // 응답 본문이 있는 표준 케이스 - 실패하면 주어진 메시지로 예외를 던진다
  const authJson = useCallback(async (path, options, failMessage) => {
    const res = await authFetch(path, options)
    if (!res.ok) throw new Error(failMessage)
    return res.json()
  }, [authFetch])

  // 서버가 실패 사유를 본문에 담아주는 케이스(닉네임 중복 등)
  const authJsonWithServerError = async (path, options, failMessage) => {
    const res = await authFetch(path, options)
    if (!res.ok) throw new Error((await res.text()) || failMessage)
    return res.json()
  }

  // 응답 본문을 쓰지 않는 케이스(DELETE, 저장만 하는 PUT). 성공/실패 판정 방식은
  // authJson과 같게 두어, 이 파일의 모든 API가 같은 모양으로 실패하도록 한다.
  const authOk = async (path, options, failMessage) => {
    const res = await authFetch(path, options)
    if (!res.ok) throw new Error(failMessage)
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
    authOk(`/api/users/me/inbody/${id}`, { method: 'DELETE' }, '삭제에 실패했어요').then(() =>
      authFetch('/api/users/me/inbody/latest')
        .then((r) => (r.status === 200 ? r.json() : null))
        .then(setInbody),
    )

  const getInbodyHistory = useCallback(() =>
    authJson('/api/users/me/inbody/history', {}, '인바디 이력을 불러오지 못했어요'), [authJson])

  // 성별/키/출생연도. 목표 칼로리·기초대사량이 이 값으로 계산되므로 저장 후 프로필 상태도 같이 갱신함
  const updateBody = ({ gender, heightCm, birthYear }) =>
    authOk('/api/users/me/profile/body', {
      method: 'PUT',
      body: JSON.stringify({ gender, heightCm, birthYear }),
    }, '신체 정보 저장에 실패했어요')
      .then(() => setProfile((prev) => ({ ...prev, gender, heightCm, birthYear })))

  // 예전엔 실패해도 예외 대신 false를 돌려줬는데, 부르는 쪽(MyPage.selectGoal)이 그 값을
  // 읽지 않아 저장이 실패해도 성공한 것처럼 목표 칼로리를 다시 계산하러 갔다. 다른 API와
  // 같이 예외를 던지게 바꿔서, 실패하면 뒤 단계가 이어지지 않는다.
  const updateGoal = (goal) =>
    authOk('/api/users/me/profile', {
      method: 'PUT',
      body: JSON.stringify({ name: profile?.name, profileImageUrl: profile?.profileImageUrl, goal }),
    }, '목표 저장에 실패했어요')
      .then(() => setProfile((prev) => ({ ...prev, goal })))

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
  //
  // followUpId는 봇이 되물은 뒤 받는 답일 때만 채운다(운동 추천). 모델에게 보낼 문장으로 감싸는 것도,
  // 앞의 두 말풍선을 이력에 남기는 것도 서버가 한다 - 여기선 사용자가 친 말 그대로 보낸다.
  const sendChat = async (message, onDelta, followUpId = null) => {
    const res = await authFetch('/api/users/me/chat', {
      method: 'POST',
      body: JSON.stringify({ message, followUpId }),
    })
    if (!res.ok || !res.body) throw new Error('답변을 받지 못했어요')

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let full = ''
    let action = null   // 스트림 끝에 한 번 오는 후속 행동 신호 (예: register_inbody)
    let links = []      // 도구가 실어 보낸 바깥 링크 (운동 추천의 국민체력100 영상)

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
        if (parsed.action) action = parsed.action
        if (parsed.links) links = parsed.links
        // 도구를 부른 턴에서 최종 답변을 다시 흘리기 직전에 온다. 그 전에 나온 조각
        // ("찾아볼게요" 같은 예고문)은 답변이 아니므로 말풍선을 비우고 다시 그린다
        if (parsed.reset) {
          full = ''
          onDelta?.(full)
        }
        if (parsed.t) {
          full += parsed.t
          onDelta?.(full)
        }
      }
    }
    return { content: full, action, links }
  }

  const getChatHistory = () =>
    authJson('/api/users/me/chat/history', {}, '대화 이력을 불러오지 못했어요')

  const clearChatHistory = () =>
    authOk('/api/users/me/chat/history', { method: 'DELETE' }, '대화 기록을 지우지 못했어요')

  const getNutrientAdvice = () =>
    authJson('/api/users/me/chat/nutrient-advice', { method: 'POST' }, '분석을 받지 못했어요')

  // 날짜별 메모. 내용을 비워서 저장하면 서버가 그 날 메모를 지운다.
  const getWorkoutMemo = useCallback((date) =>
    authJson(`/api/users/me/workout-memos/${date}`, {}, '메모를 불러오지 못했어요')
      .then((data) => data.content ?? ''), [authJson])

  // 캘린더가 "메모 있는 날"을 표시하려고 한 달치를 한 번에 받는다.
  // 값은 본문 전체가 아니라 앞 30자 미리보기다(툴팁용) - 내용은 날짜를 고를 때 따로 받아간다.
  const getWorkoutMemoMonth = useCallback((year, month) =>
    authJson(`/api/users/me/workout-memos?year=${year}&month=${month}`, {}, '메모를 불러오지 못했어요'),
    [authJson])

  const saveWorkoutMemo = (date, content) =>
    authJson(`/api/users/me/workout-memos/${date}`, {
      method: 'PUT',
      body: JSON.stringify({ content }),
    }, '메모를 저장하지 못했어요').then((data) => data.content ?? '')

  // 메뉴 버튼 답변. 자유 대화(sendChat)와 달리 서버가 도구를 직접 실행하므로 스트리밍이 아니다 -
  // 대신 라운드가 하나 줄고, 기록이 없으면 LLM 없이 즉시 응답한다.
  // { content, action } 을 그대로 넘긴다 - action 은 말풍선 아래 버튼을 그리라는 신호
  const sendChatMenu = (menuId) =>
    authJson(`/api/users/me/chat/menu/${menuId}`, { method: 'POST' }, '답변을 받지 못했어요')

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

  const getTodayMeals = useCallback((date) =>
    authJson(`/api/diet/meals/today${date ? `?date=${date}` : ''}`, {}, '식단 기록을 불러오지 못했어요'),
    [authJson])

  const getTodayTotal = useCallback((date) =>
    authJson(`/api/diet/meals/today/total${date ? `?date=${date}` : ''}`, {}, '합계를 불러오지 못했어요'),
    [authJson])

  // 달력 칸에 날짜별 칼로리를 표시하기 위한 월 단위 합계. { "2026-08-05": 1850, ... } 형태
  const getMonthCalories = useCallback((year, month) =>
    authJson(`/api/diet/meals/month?year=${year}&month=${month}`, {}, '월별 기록을 불러오지 못했어요'),
    [authJson])

  /**
   * 또래 비교(BMI / 영양). 예전엔 브라우저가 AI 서버(/ai/...)를 인증 없이 직접 불렀는데,
   * 이제 백엔드가 JWT를 확인하고 DB에서 값을 읽어 AI 서버를 대신 부른다(PeerInsightService).
   * 비교할 값을 클라이언트가 넘기지 않으므로 "내 기록"에 대한 답이라는 게 보장된다.
   *
   * 실패하거나 비교 불가면 { error } 가 담겨 오거나 null이다 - 부가 정보라 화면을 막지 않는다.
   */
  const getBmiInsight = useCallback(() =>
    authFetch('/api/users/me/insights/bmi')
      .then((res) => (res.ok ? res.json() : null))
      .catch(() => null), [authFetch])

  const getNutritionPeerCompare = useCallback((date) =>
    authFetch(`/api/users/me/insights/nutrition${date ? `?date=${date}` : ''}`)
      .then((res) => (res.ok ? res.json() : null))
      .catch(() => null), [authFetch])

  // 달력 칸에 공휴일을 표시하기 위한 월 단위 조회. { "2026-01-01": "신정", ... } 형태
  // (서버가 공공데이터포털 API로 조회 - 키 미설정이면 그냥 빈 객체가 옴)
  const getHolidays = useCallback((year, month) =>
    authJson(`/api/calendar/holidays?year=${year}&month=${month}`, {}, '공휴일 정보를 불러오지 못했어요'),
    [authJson])

  // 목표+인바디가 아직 없으면 서버가 204(본문 없음)를 주므로 null로 처리
  const getNutrientTarget = useCallback(() =>
    authFetch('/api/diet/meals/target').then((res) => (res.status === 200 ? res.json() : null)),
    [authFetch])

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
    getBmiInsight, getNutritionPeerCompare,
    logManualMeal,
    updateMeal, updateMealItemAmount, resolveMealItemMatch, deleteMeal,
    sendChat, getChatHistory, clearChatHistory, getNutrientAdvice, sendChatMenu,
    getWorkoutMemo, saveWorkoutMemo, getWorkoutMemoMonth,
  }
}

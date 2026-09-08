/**
 * AI 서버(FastAPI) 호출 헬퍼.
 *
 * auth.js와 분리한 이유: auth.js는 JWT를 붙여 백엔드(Spring)를 부르는 계층이고,
 * 여기는 인증 없는 AI 서버를 부른다. 두 서버는 주소도 인증 방식도 달라서 섞으면
 * "이 함수는 어느 서버를 부르는가"가 흐려진다.
 *
 * (2026-09-04) 또래 비교(BMI/영양)는 여기서 빠졌다 - 브라우저가 인증 없이 AI 서버를 직접
 * 두드리던 경로였고, 같은 기능을 챗봇은 이미 백엔드를 거쳐 쓰고 있어 경로가 둘이었다.
 * 이제 auth.js의 getBmiInsight / getNutritionPeerCompare(=> /api/users/me/insights/...)를 쓴다.
 * 여기 남은 건 실시간 자세 코칭처럼 브라우저가 프레임을 직접 흘려보내야 하는 호출뿐이다.
 */

// 실시간 코칭 계열은 아직 브라우저가 직접 부른다(hooks/useSquatCoachingSession.js 등).
// 이 파일에 공통 헬퍼만 남겨두면 "AI 서버를 직접 부르는 곳"이 어디인지 한눈에 보인다.
export const AI_BASE = import.meta.env.VITE_AI_BASE || 'http://localhost:8000'

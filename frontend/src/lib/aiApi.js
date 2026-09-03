/**
 * AI 서버(FastAPI) 호출 헬퍼.
 *
 * auth.js와 분리한 이유: auth.js는 JWT를 붙여 백엔드(Spring)를 부르는 계층이고,
 * 여기는 인증 없는 AI 서버를 부른다. 두 서버는 주소도 인증 방식도 달라서 섞으면
 * "이 함수는 어느 서버를 부르는가"가 흐려진다.
 *
 * 실패는 던지지 않고 null을 돌려준다 — 또래 비교는 부가 정보라, 못 가져왔다고 해서
 * 인바디나 영양소 화면 자체가 막히면 안 된다(호출부에서 그냥 섹션을 숨긴다).
 */

// auth.js 의 API_BASE 와 같은 방식 - 빌드 시 VITE_AI_BASE 로 주입, 없으면 로컬 기본값
const AI_BASE = import.meta.env.VITE_AI_BASE || 'http://localhost:8000'

/** 프로필의 성별 표기(MALE/FEMALE)를 AI 서버가 쓰는 참조 통계 표기(M/F)로 바꾼다 */
function toReferenceGender(gender) {
  if (gender === 'MALE') return 'M'
  if (gender === 'FEMALE') return 'F'
  return null
}

async function postJson(path, body) {
  try {
    const res = await fetch(`${AI_BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    return res.ok ? await res.json() : null
  } catch {
    return null // AI 서버가 꺼져 있어도 화면은 그대로 동작해야 한다
  }
}

/**
 * BMI 또래 비교 + 비만도 분류.
 * 성별/출생년도가 없으면(프로필 미입력) 비교 자체가 불가능하므로 호출하지 않는다.
 */
export function getBmiInsight({ bmi, gender, birthYear }) {
  const referenceGender = toReferenceGender(gender)
  if (!bmi || !referenceGender || !birthYear) return Promise.resolve(null)

  return postJson('/ai/inbody/bmi-insight', {
    bmi,
    gender: referenceGender,
    birth_year: birthYear,
  })
}

/** 하루 섭취량을 같은 성별·연령대 평균과 비교 */
export function getNutritionPeerCompare({ total, gender, birthYear }) {
  const referenceGender = toReferenceGender(gender)
  if (!total || !referenceGender || !birthYear) return Promise.resolve(null)

  return postJson('/ai/nutrition/peer-compare', {
    gender: referenceGender,
    birth_year: birthYear,
    energy_kcal: total.totalCalories,
    protein_g: total.totalProteinG,
    carbs_g: total.totalCarbsG,
    fat_g: total.totalFatG,
  })
}

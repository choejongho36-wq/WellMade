/**
 * 관리자 대시보드 전용 API 클라이언트. 일반 회원 쪽(auth.js의 authFetch, Authorization 헤더 +
 * localStorage 토큰)과 완전히 분리한다 — 관리자 토큰은 httpOnly 쿠키(admin_token)에만 담겨
 * 있어 JS가 애초에 값을 읽을 수 없고, 매 요청 credentials:'include'로 쿠키만 자동 전송한다.
 * 상태를 바꾸는 요청(POST)에는 쿠키 기반 CSRF 보호(XSRF-TOKEN 쿠키 → X-XSRF-TOKEN 헤더)가
 * 함께 걸려 있어야 서버가 받아준다(SecurityConfig의 adminFilterChain 참고).
 */
import { API_BASE } from './auth.js'

function readCookie(name) {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return match ? decodeURIComponent(match[1]) : null
}

async function adminFetch(path, options = {}) {
  const method = (options.method || 'GET').toUpperCase()
  const headers = { ...(options.headers || {}) }
  if (method !== 'GET' && method !== 'HEAD') {
    const csrfToken = readCookie('XSRF-TOKEN')
    if (csrfToken) headers['X-XSRF-TOKEN'] = csrfToken
  }
  if (options.body && !headers['Content-Type']) headers['Content-Type'] = 'application/json'
  return fetch(`${API_BASE}${path}`, { ...options, headers, credentials: 'include' })
}

export async function adminLogin(loginId, password) {
  const res = await adminFetch('/api/admin/auth/login', {
    method: 'POST',
    body: JSON.stringify({ loginId, password }),
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.message || '로그인에 실패했습니다')
  return data
}

export async function adminLogout() {
  await adminFetch('/api/admin/auth/logout', { method: 'POST' })
}

// 401이면 로그인 안 된 상태(정상 케이스)라 null을 반환한다 — 예외를 던지지 않는다.
export async function adminMe() {
  const res = await adminFetch('/api/admin/auth/me')
  if (!res.ok) return null
  return res.json()
}

export async function getAdminDashboard() {
  const res = await adminFetch('/api/admin/dashboard')
  if (!res.ok) throw new Error('대시보드를 불러오지 못했습니다')
  return res.json()
}

export async function getAdminReports(status, page = 0) {
  const params = new URLSearchParams({ page: String(page) })
  if (status) params.set('status', status)
  const res = await adminFetch(`/api/admin/reports?${params.toString()}`)
  if (!res.ok) throw new Error('신고 목록을 불러오지 못했습니다')
  return res.json()
}

export async function getAdminReportDetail(id) {
  const res = await adminFetch(`/api/admin/reports/${id}`)
  if (!res.ok) throw new Error('신고 상세를 불러오지 못했습니다')
  return res.json()
}

export async function approveAdminReport(id) {
  const res = await adminFetch(`/api/admin/reports/${id}/approve`, { method: 'POST' })
  if (!res.ok) throw new Error('승인 처리에 실패했습니다')
}

export async function rejectAdminReport(id) {
  const res = await adminFetch(`/api/admin/reports/${id}/reject`, { method: 'POST' })
  if (!res.ok) throw new Error('반려 처리에 실패했습니다')
}

// --- 고객센터 관리 (1:1 문의 / FAQ / 공지사항) ---

export async function getAdminInquiries(status, page = 0) {
  const params = new URLSearchParams({ page: String(page) })
  if (status) params.set('status', status)
  const res = await adminFetch(`/api/admin/inquiries?${params.toString()}`)
  if (!res.ok) throw new Error('문의 목록을 불러오지 못했습니다')
  return res.json()
}

export async function getAdminInquiryDetail(id) {
  const res = await adminFetch(`/api/admin/inquiries/${id}`)
  if (!res.ok) throw new Error('문의 상세를 불러오지 못했습니다')
  return res.json()
}

export async function answerAdminInquiry(id, answer) {
  const res = await adminFetch(`/api/admin/inquiries/${id}/answer`, {
    method: 'POST',
    body: JSON.stringify({ answer }),
  })
  if (!res.ok) throw new Error('답변 등록에 실패했습니다')
  return res.json()
}

export async function deleteAdminInquiryAnswer(id) {
  const res = await adminFetch(`/api/admin/inquiries/${id}/answer`, { method: 'DELETE' })
  if (!res.ok) throw new Error('답변 삭제에 실패했습니다')
  return res.json()
}

export async function deleteAdminInquiry(id) {
  const res = await adminFetch(`/api/admin/inquiries/${id}`, { method: 'DELETE' })
  if (!res.ok) throw new Error('문의 삭제에 실패했습니다')
}

export async function getAdminFaqs() {
  const res = await adminFetch('/api/admin/faqs')
  if (!res.ok) throw new Error('FAQ 목록을 불러오지 못했습니다')
  return res.json()
}

export async function createAdminFaq(payload) {
  const res = await adminFetch('/api/admin/faqs', { method: 'POST', body: JSON.stringify(payload) })
  if (!res.ok) throw new Error('FAQ 등록에 실패했습니다')
  return res.json()
}

export async function updateAdminFaq(id, payload) {
  const res = await adminFetch(`/api/admin/faqs/${id}`, { method: 'PUT', body: JSON.stringify(payload) })
  if (!res.ok) throw new Error('FAQ 수정에 실패했습니다')
  return res.json()
}

export async function deleteAdminFaq(id) {
  const res = await adminFetch(`/api/admin/faqs/${id}`, { method: 'DELETE' })
  if (!res.ok) throw new Error('FAQ 삭제에 실패했습니다')
}

export async function getAdminNotices(page = 0) {
  const res = await adminFetch(`/api/admin/notices?page=${page}`)
  if (!res.ok) throw new Error('공지사항 목록을 불러오지 못했습니다')
  return res.json()
}

export async function createAdminNotice(payload) {
  const res = await adminFetch('/api/admin/notices', { method: 'POST', body: JSON.stringify(payload) })
  if (!res.ok) throw new Error('공지사항 등록에 실패했습니다')
  return res.json()
}

export async function updateAdminNotice(id, payload) {
  const res = await adminFetch(`/api/admin/notices/${id}`, { method: 'PUT', body: JSON.stringify(payload) })
  if (!res.ok) throw new Error('공지사항 수정에 실패했습니다')
  return res.json()
}

export async function deleteAdminNotice(id) {
  const res = await adminFetch(`/api/admin/notices/${id}`, { method: 'DELETE' })
  if (!res.ok) throw new Error('공지사항 삭제에 실패했습니다')
}

// 브라우저 다운로드는 <a href>로 그대로 열면 되고(같은 사이트라 쿠키가 자동으로 실린다),
// fetch로 미리 받아올 필요가 없다.
export const ADMIN_REPORT_EXPORT_URL = `${API_BASE}/api/admin/reports/export`

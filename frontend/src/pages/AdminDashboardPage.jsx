import { useEffect, useState } from 'react'
import { getAdminDashboard } from '../lib/adminApi.js'
import './AdminPages.css'

function formatDateTime(iso) {
  if (!iso) return '-'
  return iso.replace('T', ' ').slice(0, 16)
}

function formatLatency(ms) {
  if (ms == null) return '—'
  return `${Math.round(ms).toLocaleString()}ms`
}

export default function AdminDashboardPage() {
  const [stats, setStats] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getAdminDashboard().then(setStats).catch((err) => setError(err.message))
  }, [])

  return (
    <>
      <h1>대시보드</h1>
      {error && <p className="admin-error-text">{error}</p>}
      {stats && (
        <>
          <div className="admin-cards admin-cards-3">
            <div className="admin-card">
              <div className="label">전체 회원</div>
              <div className="value">{stats.summary.totalUsers.toLocaleString()}</div>
            </div>
            <div className="admin-card">
              <div className="label">오늘 신규가입</div>
              <div className="value">{stats.summary.todaySignups.toLocaleString()}</div>
            </div>
            <div className="admin-card">
              <div className="label">오늘 활성 사용자(DAU)</div>
              <div className="value">{stats.summary.dau.toLocaleString()}</div>
            </div>
          </div>

          <div className="admin-section-grid">
            <div className="admin-panel">
              <h2>인바디(Inbody)</h2>
              <div className="admin-stat-grid">
                <div className="admin-stat">
                  <div className="label">이번 주 신규 등록</div>
                  <div className="value">{stats.inbody.weekNewRecords.toLocaleString()}</div>
                </div>
              </div>
              <div className="admin-subheading">최근 인바디 등록</div>
              {stats.inbody.recent.length > 0 ? (
                <ul className="admin-mini-list">
                  {stats.inbody.recent.map((r) => (
                    <li key={r.id}>
                      <span>{r.userEmail ?? '(이메일 없음)'}</span>
                      <span>{formatDateTime(r.createdAt)}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="admin-empty-text">최근 등록된 인바디 기록이 없습니다.</p>
              )}
            </div>

            <div className="admin-panel">
              <h2>챗봇(Chat)</h2>
              <div className="admin-stat-grid">
                <div className="admin-stat">
                  <div className="label">오늘 대화 수</div>
                  <div className="value">{stats.chat.todayConversations.toLocaleString()}</div>
                </div>
                <div className="admin-stat">
                  <div className="label">오늘 챗봇 사용자</div>
                  <div className="value">{stats.chat.todayActiveUsers.toLocaleString()}</div>
                </div>
                <div className="admin-stat">
                  <div className="label">사용자당 평균 메시지</div>
                  <div className="value">{stats.chat.avgMessagesPerUser.toFixed(1)}</div>
                </div>
              </div>
              <div className="admin-subheading">오늘 많이 호출된 도구</div>
              {stats.chat.topTools.length > 0 ? (
                <ul className="admin-mini-list">
                  {stats.chat.topTools.map((t) => (
                    <li key={t.toolName}>
                      <span>{t.toolName}</span>
                      <span>{t.count.toLocaleString()}회</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="admin-empty-text">오늘 호출된 도구가 없습니다.</p>
              )}
            </div>

            <div className="admin-panel">
              <h2>AI 운영 모니터링</h2>
              <p className="admin-panel-note">
                WellMade 챗봇은 자체 호스팅한 Ollama 모델을 씁니다(GPU 인스턴스가 평소 꺼져 있는 게
                정상 운영 방식이라, 호출 실패 시 아래처럼 정해진 안내문으로 답합니다).
              </p>
              <div className="admin-stat-grid">
                <div className="admin-stat">
                  <div className="label">오늘 LLM 호출</div>
                  <div className="value">{stats.monitoring.todayLlmCalls.toLocaleString()}</div>
                </div>
                <div className="admin-stat">
                  <div className="label">오늘 폴백 발동</div>
                  <div className="value">{stats.monitoring.todayLlmFallbacks.toLocaleString()}</div>
                </div>
                <div className="admin-stat">
                  <div className="label">평균 응답 지연</div>
                  <div className="value">{formatLatency(stats.monitoring.avgLatencyMs)}</div>
                </div>
                <div className="admin-stat">
                  <div className="label">오늘 도구 호출 / 실패</div>
                  <div className="value">
                    {stats.monitoring.todayToolCalls.toLocaleString()} / {stats.monitoring.todayToolFailures.toLocaleString()}
                  </div>
                </div>
              </div>
            </div>

            <div className="admin-panel">
              <h2>최근 가입자</h2>
              {stats.recent.recentUsers.length > 0 ? (
                <table className="admin-table">
                  <thead>
                    <tr>
                      <th>이메일</th>
                      <th>가입일시</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stats.recent.recentUsers.map((u) => (
                      <tr key={u.id}>
                        <td>{u.email ?? '(이메일 없음)'}</td>
                        <td>{formatDateTime(u.createdAt)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p className="admin-empty-text">최근 가입자가 없습니다.</p>
              )}
            </div>
          </div>
        </>
      )}
    </>
  )
}

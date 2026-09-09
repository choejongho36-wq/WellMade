/**
 * 운동 기록 페이지 (/exercises-history, 2026-09-09 신규) — 과거 스쿼트 세션 리포트를
 * 날짜별로 다시 볼 수 있는 페이지.
 *
 * 실시간 코칭 화면(SquatCoachingPage.jsx)의 카메라/MediaPipe 판정 로직과는 무관해서
 * useSquatCoachingSession.js를 쓰지 않고, 저장된 이력(squatSessionHistory.js)과 날짜별
 * 누적 통계(squatDailyStats.js)만 읽어서 보여준다 — 그래야 이 페이지 번들에 무거운 포즈
 * 인식 코드가 안 딸려온다.
 *
 * 왼쪽 달력에서 날짜를 클릭하거나 "최근 세션" 목록에서 세션을 클릭하면 그 날짜가
 * 선택되고, 오른쪽 "스쿼트 세션 요약"이 그 날짜로 다시 그려진다. 하루에 여러 세트를
 * 했으면 그 세트들을 합쳐서(점수 재평균, 부위별 이상 횟수 합산) 보여준다
 * (aggregateSessionsByDate, squatSessionHistory.js 참고). 처음 열렸을 땐 기록이 있는 가장
 * 최근 날짜를 기본으로 보여준다.
 *
 * "자세 분석 결과" 4타일(스쿼트 깊이=엉덩이 각도, 무릎 각도, 상체 기울기=시선·목 기울기,
 * 좌우 균형=무릎모임)의 기준 범위는 목업의 임의 숫자가 아니라 실제 AI 판정에 쓰는
 * squatPose.js의 ANALYSIS_METRICS를 그대로 쓴다 — 사진 코칭 페이지의 "상세 보기"
 * (MetricsDetailPanel)와 같은 원칙. 좌우 균형은 정면 단계를 진행한 세션이 있어야
 * 계산되므로, 없으면 안내 문구로 대체한다.
 */
import { useState } from 'react'
import PageShell from '../components/PageShell.jsx'
import SquatGoalCalendar from '../components/SquatGoalCalendar.jsx'
import RecentSessionsList, { formatDateWithWeekday } from '../components/RecentSessionsList.jsx'
import { ANALYSIS_METRICS, PART_LABELS } from '../lib/squatPose.js'
import { loadSquatSessionHistory, aggregateSessionsByDate, latestSessionDate } from '../lib/squatSessionHistory.js'
import { loadSquatDailyStats, todayDateKey, formatDateKey } from '../lib/squatDailyStats.js'
import { getExerciseGoal } from '../lib/exerciseGoals.js'
import './ExerciseHistoryPage.css'

const WEEKDAY_KO = ['일', '월', '화', '수', '목', '금', '토']

function formatSessionDuration(sec) {
  const total = Math.max(0, Math.round(sec ?? 0))
  const m = Math.floor(total / 60)
  const s = total % 60
  return m > 0 ? `${m}분 ${s}초` : `${s}초`
}

function formatMinutesFromSec(sec) {
  if (!sec) return '0분'
  return `${Math.max(1, Math.round(sec / 60))}분`
}

// 선택한 날짜가 속한 주(일~토)의 날짜 7개를 반환한다 — "이번 주 운동 현황"/"운동 목표
// 달성 현황"에 쓴다.
function weekDatesOf(dateKey) {
  const d = new Date(`${dateKey}T00:00:00`)
  const sunday = new Date(d)
  sunday.setDate(d.getDate() - d.getDay())
  const days = []
  for (let i = 0; i < 7; i++) {
    const day = new Date(sunday)
    day.setDate(sunday.getDate() + i)
    days.push(formatDateKey(day))
  }
  return days
}

function scoreClass(score) {
  return score >= 80 ? 'is-good' : 'is-ok'
}
function scoreLabel(score) {
  return score >= 80 ? '양호' : '보통'
}

// 자세 점수 도넛 — SquatCoachingPage.jsx의 NormalRatioMeter와 톤을 맞췄다(80점 기준으로
// 초록/파랑만 다르다 — 파랑은 숙련자 토글·"보통" 배지와 색을 통일했다).
function ScoreDonut({ score }) {
  const pct = Math.max(0, Math.min(100, score ?? 0))
  const isGood = pct >= 80
  const ringColor = isGood ? '#2eb872' : '#2f6fed'
  const ringWash = isGood ? 'rgba(46, 184, 114, 0.16)' : 'rgba(47, 111, 237, 0.14)'
  const r = 30
  const circumference = 2 * Math.PI * r
  const offset = circumference * (1 - pct / 100)
  return (
    <svg width="72" height="72" viewBox="0 0 72 72">
      <circle cx="36" cy="36" r={r} fill="none" stroke={ringWash} strokeWidth="8" />
      <circle
        cx="36" cy="36" r={r} fill="none" stroke={ringColor} strokeWidth="8" strokeLinecap="round"
        strokeDasharray={circumference} strokeDashoffset={offset} transform="rotate(-90 36 36)"
      />
      <text x="36" y="40" textAnchor="middle" fontSize="16" fontWeight="800" fill="#111">{pct}</text>
      <text x="36" y="52" textAnchor="middle" fontSize="8" fill="#8c8b88">점</text>
    </svg>
  )
}

const HISTORY_METRIC_KEYS = [
  { key: 'hip_angle', title: '스쿼트 깊이' },
  { key: 'knee_angle', title: '무릎 각도' },
  { key: 'shoulder_forward_lean_deg', title: '상체 기울기' },
  { key: 'knee_valgus_ratio', title: '좌우 균형' },
]

function pickMetric(key) {
  return ANALYSIS_METRICS.find((m) => m.field === key)
}

// 자세 분석 결과 4타일(기본 화면).
function PoseMetricTiles({ avgMetrics }) {
  return (
    <div className="hist-metric-tiles">
      {HISTORY_METRIC_KEYS.map(({ key, title }) => {
        const meta = pickMetric(key)
        const value = avgMetrics[key]
        if (value == null) {
          return (
            <div key={key} className="hist-metric-tile hist-metric-tile-empty">
              <div className="hist-metric-tile-title">{title}</div>
              <p className="hist-metric-tile-empty-text">
                {meta.frontalOnly ? '정면 촬영이 있어야 계산돼요' : '깊게 앉은 구간이 부족해 계산 못 했어요'}
              </p>
            </div>
          )
        }
        const [okMin, okMax] = meta.ok
        const isOk = value >= okMin && value <= okMax
        return (
          <div key={key} className={`hist-metric-tile${isOk ? '' : ' is-warn'}`}>
            <div className="hist-metric-tile-title">{title}</div>
            <div className="hist-metric-tile-value">
              {value.toFixed(meta.unit === '°' ? 0 : 2)}{meta.unit}
            </div>
            <div className={`hist-metric-tile-badge${isOk ? '' : ' is-warn'}`}>{isOk ? '양호' : '주의'}</div>
            <p className="hist-metric-tile-range">기준 {meta.rangeText}</p>
          </div>
        )
      })}
    </div>
  )
}

// "더보기"를 누르면 나오는 막대그래프 버전 — 사진 코칭 페이지의 "상세 보기"
// (MetricsDetailPanel)와 같은 방식(scale 전체 범위 안에 ok 구간을 칠하고 실제 값 위치에
// 마커)을 쓴다.
function PoseMetricBars({ avgMetrics }) {
  return (
    <div className="hist-metric-bars">
      {HISTORY_METRIC_KEYS.map(({ key, title }) => {
        const meta = pickMetric(key)
        const value = avgMetrics[key]
        if (value == null) {
          return (
            <div key={key} className="hist-metric-bar-row">
              <div className="hist-metric-bar-head">
                <span className="hist-metric-bar-label">{title}</span>
              </div>
              <p className="hist-metric-bar-caption">
                {meta.frontalOnly ? '정면 촬영이 있어야 계산돼요.' : '깊게 앉은 구간이 부족해 계산하지 못했어요.'}
              </p>
            </div>
          )
        }
        const [scaleMin, scaleMax] = meta.scale
        const [okMin, okMax] = meta.ok
        const toPercent = (n) => ((Math.min(scaleMax, Math.max(scaleMin, n)) - scaleMin) / (scaleMax - scaleMin)) * 100
        const okLeft = toPercent(okMin)
        const okWidth = toPercent(okMax) - okLeft
        const markerLeft = toPercent(value)
        return (
          <div key={key} className="hist-metric-bar-row">
            <div className="hist-metric-bar-head">
              <span className="hist-metric-bar-label">{title}</span>
              <span className="hist-metric-bar-value">{value.toFixed(meta.unit === '°' ? 1 : 2)}{meta.unit}</span>
            </div>
            <div className="hist-metric-bar-track">
              <div className="hist-metric-bar-ok-zone" style={{ left: `${okLeft}%`, width: `${okWidth}%` }} />
              <div className="hist-metric-bar-marker" style={{ left: `${markerLeft}%` }} />
            </div>
            <p className="hist-metric-bar-caption">{meta.rangeText}</p>
          </div>
        )
      })}
    </div>
  )
}

const ALL_PARTS = Object.keys(PART_LABELS).filter((p) => p !== 'data')

// AI 코칭 피드백 — "잘된 점"(그날 이상이 한 번도 없었던 부위)과 "개선할 점"(이상이 잦았던
// 부위)을 부위별 이상 횟수(issueCounts)에서 자동으로 뽑는다. 서버가 세션마다 이미
// 계산해주는 판정(realtime.py의 issues[].part)을 재해석하는 수준이라 새 AI 로직은 아니다.
function AiFeedback({ issueCounts }) {
  const problemParts = Object.entries(issueCounts).sort((a, b) => b[1] - a[1])
  const goodParts = ALL_PARTS.filter((p) => !issueCounts[p])
  return (
    <div className="hist-feedback-row">
      <div className="hist-feedback-card hist-feedback-good">
        <div className="hist-feedback-title">👍 잘된 점</div>
        {goodParts.length > 0 ? (
          <ul>
            {goodParts.slice(0, 3).map((p) => (
              <li key={p}>{PART_LABELS[p] ?? p} 자세를 안정적으로 유지했어요.</li>
            ))}
          </ul>
        ) : (
          <p>다음 세션에서 좋은 점을 더 찾아볼게요.</p>
        )}
      </div>
      <div className="hist-feedback-card hist-feedback-warn">
        <div className="hist-feedback-title">⚠️ 개선할 점</div>
        {problemParts.length > 0 ? (
          <ul>
            {problemParts.slice(0, 3).map(([p, count]) => (
              <li key={p}>{PART_LABELS[p] ?? p} 이상이 {count}회 감지됐어요.</li>
            ))}
          </ul>
        ) : (
          <p>특별히 반복된 이상 자세가 없었어요.</p>
        )}
      </div>
    </div>
  )
}

// 최근 세션들의 점수 추이 — SquatCoachingPage.jsx의 SessionTrendChart와 같은 SVG 꺾은선
// 방식을 쓰되, normal_ratio 대신 score(자세+목표 달성 종합 점수)를 그린다.
function ScoreTrendChart({ history }) {
  const recent = history.filter((h) => h.score != null).slice(-5)
  if (recent.length < 2) return null
  const width = 320
  const height = 120
  const padLeft = 26
  const padRight = 10
  const top = 14
  const bottom = 96
  const n = recent.length
  const stepX = n > 1 ? (width - padRight - padLeft) / (n - 1) : 0
  const points = recent.map((h, i) => ({
    x: padLeft + stepX * i,
    y: bottom - (h.score / 100) * (bottom - top),
    score: h.score,
  }))
  const pointsAttr = points.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
  const delta = points[points.length - 1].score - points[0].score

  return (
    <div className="hist-chart-card">
      <div className="hist-chart-title">
        자세 점수 추이 <span className="hist-chart-sub">최근 {n}회</span>
        {delta !== 0 && (
          <span className={`hist-trend-delta${delta > 0 ? ' is-up' : ' is-down'}`}>{delta > 0 ? '+' : ''}{delta}점</span>
        )}
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} className="hist-trend-svg" preserveAspectRatio="xMidYMid meet">
        <line x1={padLeft} y1={top} x2={width - padRight} y2={top} stroke="#e5e3dd" strokeWidth="1" />
        <line x1={padLeft} y1={bottom} x2={width - padRight} y2={bottom} stroke="#c3c2b7" strokeWidth="1" />
        <polyline points={pointsAttr} fill="none" stroke="#2f6fed" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        {points.map((p, i) => (
          <circle key={i} cx={p.x} cy={p.y} r={i === points.length - 1 ? 5 : 4} fill="#2f6fed" stroke="#fff" strokeWidth="2" />
        ))}
      </svg>
    </div>
  )
}

function ExerciseHistoryPage() {
  const [history] = useState(() => loadSquatSessionHistory())
  const [dailyStats] = useState(() => loadSquatDailyStats())
  const [goal] = useState(() => getExerciseGoal('squat'))
  const [selectedDate, setSelectedDate] = useState(() => latestSessionDate(history) ?? todayDateKey())
  const [showBars, setShowBars] = useState(false)

  const agg = aggregateSessionsByDate(history, selectedDate)
  const dayStat = dailyStats[selectedDate]
  const totalReps = dayStat?.total_reps ?? 0
  const totalSets = dayStat?.total_sets ?? 0
  const totalDuration = dayStat?.total_duration_sec ?? 0
  const avgDurationPerSet = totalSets > 0 ? totalDuration / totalSets : 0
  const goalTotal = goal ? goal.targetReps * goal.targetSets : null
  const achievementPct = goalTotal ? Math.min(100, Math.round((totalReps / goalTotal) * 100)) : null

  // (2026-09-09) "이번 주 목표"는 하루 목표(회수×세트)를 7일 기준으로 단순 환산한 값이다 —
  // 매일 운동한다고 가정한 근사치라는 걸 밝혀둔다. 실제로 요일별 계획이 생기면 그때
  // 정교화하면 된다.
  const week = weekDatesOf(selectedDate)
  const weekReps = week.reduce((sum, d) => sum + (dailyStats[d]?.total_reps ?? 0), 0)
  const weekGoalTotal = goal ? goal.targetReps * goal.targetSets * 7 : null
  const weekPct = weekGoalTotal ? Math.min(100, Math.round((weekReps / weekGoalTotal) * 100)) : null

  const recentSorted = [...history].reverse()

  return (
    <PageShell>
      <div className="page-eyebrow-row">
        <div className="page-index-tag">EXERCISE HISTORY</div>
      </div>
      <div className="section-head">
        <div className="section-title">운동 기록</div>
      </div>

      <div className="hist-layout">
        <div className="hist-left-col">
          <SquatGoalCalendar dailyStats={dailyStats} goal={goal} onSelectDate={setSelectedDate} selectedDate={selectedDate} />
          <RecentSessionsList sessions={recentSorted} onSelect={setSelectedDate} selectedDate={selectedDate} title="최근 세션" />
        </div>

        <div className="hist-right-col">
          {agg.entries.length === 0 ? (
            <div className="hist-empty-card">
              <p>{selectedDate}에는 운동 기록이 없어요. 달력이나 최근 세션에서 다른 날짜를 골라보세요.</p>
            </div>
          ) : (
            <>
              <div className="hist-summary-card">
                <div className="hist-summary-title">스쿼트 세션 요약</div>
                <div className="hist-summary-stats">
                  <div className="hist-summary-stat hist-summary-stat-score">
                    <ScoreDonut score={agg.avgScore ?? 0} />
                    <div>
                      <div className="hist-summary-stat-label">자세 점수</div>
                      <div className={`hist-summary-stat-badge ${scoreClass(agg.avgScore ?? 0)}`}>
                        {scoreLabel(agg.avgScore ?? 0)}
                      </div>
                    </div>
                  </div>
                  <div className="hist-summary-stat">
                    <div className="hist-summary-stat-label">총 횟수</div>
                    <div className="hist-summary-stat-value">{totalReps}회</div>
                    <div className="hist-summary-stat-sub">{totalSets}세트</div>
                  </div>
                  <div className="hist-summary-stat">
                    <div className="hist-summary-stat-label">운동 시간</div>
                    <div className="hist-summary-stat-value">{formatSessionDuration(totalDuration)}</div>
                    <div className="hist-summary-stat-sub">평균 {formatMinutesFromSec(avgDurationPerSet)}/세트</div>
                  </div>
                  <div className="hist-summary-stat">
                    <div className="hist-summary-stat-label">목표 달성률</div>
                    <div className="hist-summary-stat-value">{achievementPct != null ? `${achievementPct}%` : '-'}</div>
                    <div className="hist-summary-stat-sub">
                      {achievementPct != null ? `${totalReps}/${goalTotal}회` : '목표 미설정'}
                    </div>
                  </div>
                </div>
              </div>

              <div className="hist-analysis-card">
                <div className="hist-analysis-head">
                  <span className="hist-analysis-title">자세 분석 결과</span>
                  <span className="hist-analysis-date">{formatDateWithWeekday(selectedDate)}</span>
                  <button type="button" className="hist-detail-toggle-btn" onClick={() => setShowBars((v) => !v)}>
                    {showBars ? '간단히 보기' : '더보기 ›'}
                  </button>
                </div>
                {showBars ? <PoseMetricBars avgMetrics={agg.avgMetrics} /> : <PoseMetricTiles avgMetrics={agg.avgMetrics} />}
              </div>

              <div className="hist-feedback-section">
                <div className="hist-section-title">AI 코칭 피드백</div>
                <AiFeedback issueCounts={agg.issueCounts} />
                {agg.mostFrequentIssuePart && (
                  <div className="hist-tip-bar">
                    💡 다음 운동을 위한 TIP: {PART_LABELS[agg.mostFrequentIssuePart] ?? agg.mostFrequentIssuePart} 쪽을 다음 세션에서 조금 더 천천히, 신경 써서 움직여보세요.
                  </div>
                )}
              </div>

              {/* (2026-09-09 수정) 원래 목업 순서대로 "세트별 기록 + 자세 점수 추이"를
                  한 줄로, "운동 목표 달성 현황 + 이번 주 운동 현황"을 그다음 줄로 짝지었다
                  — 전에는 점수 추이가 목표 달성 현황과 묶이고 이번 주 현황만 따로 떨어져
                  있었다. */}
              <div className="hist-row-2col">
                <div className="hist-sets-card">
                  <div className="hist-section-title">세트별 기록</div>
                  <table className="hist-sets-table">
                    <thead>
                      <tr>
                        <th>세트</th>
                        <th>횟수</th>
                        <th>자세 점수</th>
                        <th>운동 시간</th>
                      </tr>
                    </thead>
                    <tbody>
                      {agg.entries.map((entry, i) => (
                        <tr key={i}>
                          <td>{i + 1}세트</td>
                          <td>{entry.reps ?? '-'}회</td>
                          <td>{entry.score ?? Math.round((entry.normal_ratio ?? 0) * 100)}점</td>
                          <td>{formatSessionDuration(entry.durationSec)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <ScoreTrendChart history={history} />
              </div>

              <div className="hist-row-2col">
                <div className="hist-goal-card">
                  <div className="hist-section-title">운동 목표 달성 현황</div>
                  {weekGoalTotal ? (
                    <>
                      <div className="hist-goal-numbers">
                        <span>이번 주 목표 <b>{weekGoalTotal}회</b></span>
                        <span>실제 운동 <b>{weekReps}회</b></span>
                        <span className="hist-goal-pct">{weekPct}%</span>
                      </div>
                      <div className="hist-goal-bar">
                        <div className="hist-goal-bar-fill" style={{ width: `${weekPct}%` }} />
                      </div>
                    </>
                  ) : (
                    <p className="hist-empty-text">마이페이지에서 목표를 설정하면 이번 주 달성 현황이 보여요.</p>
                  )}
                </div>

                <div className="hist-week-card">
                  <div className="hist-section-title">이번 주 운동 현황</div>
                  <div className="hist-week-row">
                    {week.map((d, i) => {
                      const stat = dailyStats[d]
                      // (2026-09-09 수정) 세트 개수가 아니라 그날 총 렙수 기준으로 달성
                      // 여부를 판단한다 — SquatGoalCalendar.jsx와 기준을 통일했다.
                      const goalTotalReps = goal != null ? goal.targetReps * goal.targetSets : null
                      const met = goalTotalReps != null && stat != null && stat.total_reps >= goalTotalReps
                      const hasData = stat != null && stat.total_reps > 0
                      return (
                        <div key={d} className="hist-week-day">
                          <div className="hist-week-day-label">{WEEKDAY_KO[i]}</div>
                          <div className={`hist-week-day-dot${met ? ' is-met' : hasData ? ' is-partial' : ''}`}>
                            {met ? '✓' : ''}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </PageShell>
  )
}

export default ExerciseHistoryPage

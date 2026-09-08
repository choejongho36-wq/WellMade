/**
 * 실시간 스쿼트 코칭 페이지 (서비스 흐름도의 ②-B 실시간 코칭 + ③ 세션 종료).
 *
 * 캘리브레이션(고관절 유연성 측정)과 사진 코칭(②-A)은 이 페이지의 범위가 아니다 —
 * 캘리브레이션 측정 UI·정면 사진 촬영·동년배 비교 인사이트(AI-15)는 다른 팀원 담당
 * 영역이고(app/main.py의 posture_insight 엔드포인트 docstring, pages/MlTestPage.jsx의
 * 파일 상단 주석 참고), 사진 코칭(구 AI-03)은 백엔드에서 완전히 삭제되며 다른 팀원
 * 담당으로 정리된 바 있다. 이 페이지는 측면 카메라 한 대로 진행하는 실시간 코칭
 * 세션만 다룬다 — hip_calibration 없이 호출하면 서버가 고정 NORMAL_RANGES 기준으로
 * 판정한다(app/schemas.py HipFlexibilityCalibration 참고, 하위 호환 동작).
 *
 * 화면 흐름: idle(시작 전 안내) → active(웹캠 · 스켈레톤 · 실시간 피드백 · TTS) →
 * report(세션 리포트). 실제 판정/API 연동 로직은 hooks/useSquatCoachingSession.js가
 * 전담하고, 이 파일은 그 상태를 화면에 그리는 역할만 한다.
 */

import { useState } from 'react'
import PageShell from '../components/PageShell.jsx'
import { useSquatCoachingSession } from '../hooks/useSquatCoachingSession.js'
import { PART_LABELS } from '../lib/squatPose.js'
import { formatDateKey, todayDateKey } from '../lib/squatDailyStats.js'
import './squatShared.css'
import './SquatCoachingPage.css'

function IdleView({ onStart, cameraError }) {
  return (
    <div className="squat-card squat-idle">
      <h2 className="squat-idle-title">실시간 스쿼트 코칭을 시작할게요</h2>
      <ol className="squat-idle-steps">
        <li>휴대폰이나 노트북 카메라를 측면(옆모습)이 보이도록 세워주세요.</li>
        <li>발끝부터 머리까지 화면에 다 들어오게 한 걸음 물러나 주세요.</li>
        <li>시작 버튼을 누르면 카메라 권한을 요청해요.</li>
        <li>스쿼트를 하는 동안 실시간으로 자세를 확인해요.</li>
        <li>자세가 정상인지 아닌지 음성으로 바로바로 안내해드려요.</li>
        <li>바른 자세를 목표 시간만큼 유지하면 자동으로 세션이 끝나요. (언제든 "운동 종료" 버튼으로 직접 끝낼 수도 있어요.)</li>
      </ol>
      {cameraError && <p className="squat-error">{cameraError}</p>}
      <button className="squat-btn squat-btn-primary" onClick={onStart}>
        카메라 켜고 시작하기
      </button>
    </div>
  )
}

function ActiveView({ session }) {
  const {
    videoRef,
    canvasRef,
    judgeResult,
    judgeError,
    fullBodyWarning,
    coachingLog,
    sessionStage,
    bufferCount,
    bufferMax,
    endCheck,
    ttsEnabled,
    setTtsEnabled,
    endSession,
  } = session

  const isWarmingUp = bufferCount < 3
  const isFront = sessionStage === 'front'
  // 정면 단계는 무릎모임(knee_valgus)만 판정하므로 측면 전용 필드(isDeepHold/
  // standingStepText)는 보지 않고 judgeResult.view로 갈라서 별도 문구를 쓴다
  // (useSquatCoachingSession.js 참고). judgeResult.is_normal이어도 실제로 앉은
  // 상태(isDeepHold)가 아니면(측면) "지금 자세를 유지하세요"를 보여주지 않고, 서 있을
  // 때는 대신 스쿼트 방법을 한 단계씩 안내하는 문구(standingStepText)를 보여준다.
  const feedbackText = judgeError
    ? judgeError
    : fullBodyWarning
      ? '전신이 나오게 뒤로 한 발짝 물러나주세요'
      : isWarmingUp
        ? '자세를 인식하고 있어요...'
        : judgeResult
          ? judgeResult.view === 'front'
            ? judgeResult.is_normal
              ? '좋아요, 무릎이 발끝 방향을 잘 유지하고 있어요'
              : (judgeResult.issues?.[0]?.message ?? '무릎 모임을 확인해주세요')
            : judgeResult.is_normal
              ? judgeResult.isDeepHold
                ? '좋아요, 지금 자세를 유지하세요'
                : (judgeResult.standingStepText || '자세를 인식하고 있어요...')
              : (judgeResult.issues?.[0]?.message ?? '자세를 확인해주세요')
          : '자세를 인식하고 있어요...'

  const feedbackState = judgeError
    ? 'error'
    : fullBodyWarning
      ? 'warn'
      : isWarmingUp || !judgeResult
        ? 'warming'
        : judgeResult.view === 'front'
          ? (judgeResult.is_normal ? 'ok' : 'warn')
          : judgeResult.is_normal
            ? (judgeResult.isDeepHold ? 'ok' : 'guide')
            : 'warn'

  return (
    <div className="squat-active-layout">
      <div className="squat-active">
        <div className="squat-stage-label">
          {isFront ? '2단계 · 정면 코칭 진행 중 (무릎모임 확인)' : '1단계 · 측면 코칭 진행 중'}
        </div>
        <div className="squat-camera-wrap">
          <video ref={videoRef} muted playsInline className="squat-video" />
          <canvas ref={canvasRef} className="squat-overlay" />
          <div className={`squat-feedback-badge squat-feedback-${feedbackState}`}>{feedbackText}</div>
        </div>

        {judgeResult && !isWarmingUp && judgeResult.issues?.length > 1 && (
          <div className="squat-card squat-issue-list">
            {judgeResult.issues.map((issue, i) => (
              <div key={i} className="squat-issue-row">
                · [{PART_LABELS[issue.part] ?? issue.part}] {issue.message}
              </div>
            ))}
          </div>
        )}

        {endCheck && (
          <p className="squat-progress-note">
            최근 {endCheck.window_duration_sec.toFixed(0)}초 구간 정상 자세 비율{' '}
            <b>{Math.round(endCheck.normal_ratio * 100)}%</b>
            {endCheck.reason === 'target_sustained' && ' · 목표 도달! 곧 세션이 끝나요'}
          </p>
        )}

        <div className="squat-controls">
          <label className="squat-tts-toggle">
            <input type="checkbox" checked={ttsEnabled} onChange={(e) => setTtsEnabled(e.target.checked)} />
            음성 안내 (TTS)
          </label>
          <button className="squat-btn squat-btn-outline" onClick={endSession}>
            운동 종료
          </button>
        </div>

        <p className="squat-buffer-note">
          인식 프레임 {bufferCount}/{bufferMax}
        </p>
      </div>

      <CoachingLogPanel log={coachingLog} />
    </div>
  )
}

// 오른쪽 코칭 로그 패널 — 세션 동안 화면 배지/음성으로 나간 멘트를 시간순(최신이 위)으로
// 보여준다. 데이터는 useSquatCoachingSession.js의 coachingLog 참고.
function CoachingLogPanel({ log }) {
  return (
    <div className="squat-coaching-log">
      <div className="squat-coaching-log-title">코칭 로그</div>
      {log.length === 0 ? (
        <p className="squat-coaching-log-empty">아직 기록이 없어요.</p>
      ) : (
        log.map((entry) => (
          <div
            key={entry.id}
            className={`squat-coaching-log-item${entry.state === 'warn' ? ' squat-coaching-log-item-warn' : ''}`}
          >
            <span className="squat-coaching-log-time">{entry.time}</span>
            <span className="squat-coaching-log-text">{entry.text}</span>
          </div>
        ))
      )}
    </div>
  )
}

// 세션 시간(초)을 리포트 카드에 보여줄 형태로 바꾼다 — "1분 12초" / "32초".
function formatSessionDuration(sec) {
  const total = Math.max(0, Math.round(sec))
  const m = Math.floor(total / 60)
  const s = total % 60
  return m > 0 ? `${m}분 ${s}초` : `${s}초`
}

// 세션 이력의 날짜(YYYY-MM-DD)를 그래프 축에 쓸 짧은 형태로 바꾼다 — "09/07".
function formatShortDate(dateStr) {
  const parts = String(dateStr).split('-')
  if (parts.length !== 3) return dateStr
  return `${parts[1]}/${parts[2]}`
}

// 정상 자세 비율을 도넛 링으로 보여주고, 지난 세션 대비 증감을 함께 표시한다.
function NormalRatioMeter({ report }) {
  const pct = Math.round(report.normal_ratio * 100)
  const isGood = report.normal_ratio >= 0.8
  const ringColor = isGood ? '#2eb872' : '#da291c'
  const ringWash = isGood ? 'rgba(46, 184, 114, 0.16)' : 'rgba(218, 41, 28, 0.14)'
  const r = 48
  const circumference = 2 * Math.PI * r
  const offset = circumference * (1 - report.normal_ratio)

  return (
    <div className="squat-meter-card">
      <svg className="squat-meter-ring" width="104" height="104" viewBox="0 0 112 112">
        <circle cx="56" cy="56" r={r} fill="none" stroke={ringWash} strokeWidth="12" />
        <circle
          cx="56"
          cy="56"
          r={r}
          fill="none"
          stroke={ringColor}
          strokeWidth="12"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          transform="rotate(-90 56 56)"
        />
        <text x="56" y="52" textAnchor="middle" fontSize="20" fontWeight="700" fill="#111">{pct}%</text>
        <text x="56" y="70" textAnchor="middle" fontSize="10" fill="#8c8b88">정상 자세</text>
      </svg>
      <div className="squat-meter-text">
        <div className="squat-meter-title">정상 자세 비율</div>
        <div className="squat-meter-caption">
          {formatSessionDuration(report.session_duration_sec)} · 총 {report.total_reps}회 중 {report.normal_reps}회 정상 판정
        </div>
        {report.previous_normal_ratio != null && report.improvement_vs_previous_pct != null && (
          <div className="squat-meter-delta">
            {report.improvement_vs_previous_pct > 0 ? '▲' : report.improvement_vs_previous_pct < 0 ? '▼' : '·'}
            {' '}
            {Math.abs(report.improvement_vs_previous_pct).toFixed(1)}%p{' '}
            <span className="prev">지난 세션({Math.round(report.previous_normal_ratio * 100)}%) 대비</span>
          </div>
        )}
      </div>
    </div>
  )
}

// 부위별 이상 발생 빈도를 가로 막대그래프로 보여준다.
function IssuePartBarChart({ counts, mostFrequent }) {
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1])
  const max = entries.length > 0 ? entries[0][1] : 1
  return (
    <div className="squat-chart-card">
      <div className="squat-chart-title">부위별 이상 발생 빈도</div>
      {mostFrequent && (
        <div className="squat-chart-sub">가장 빈번한 이상 부위: {PART_LABELS[mostFrequent] ?? mostFrequent}</div>
      )}
      {entries.map(([part, count]) => (
        <div key={part} className="squat-bar-row">
          <div className="squat-bar-label">{PART_LABELS[part] ?? part}</div>
          <div className="squat-bar-track">
            <div className="squat-bar-fill" style={{ width: `${Math.round((count / max) * 100)}%` }} />
            <div className="squat-bar-value" style={{ left: `calc(${Math.round((count / max) * 100)}% + 8px)` }}>
              {count}회
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

// 최근 세션들의 정상 자세 비율을 날짜별로 비교하는 꺾은선 그래프.
function SessionTrendChart({ history }) {
  const width = 340
  const height = 140
  const padLeft = 28
  const padRight = 12
  const top = 16
  const bottom = 116
  const n = history.length
  const stepX = n > 1 ? (width - padRight - padLeft) / (n - 1) : 0
  const points = history.map((h, i) => ({
    x: padLeft + stepX * i,
    y: bottom - h.normal_ratio * (bottom - top),
    ratio: h.normal_ratio,
    date: h.date,
  }))
  const pointsAttr = points.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
  const last = points[points.length - 1]

  return (
    <div className="squat-chart-card">
      <div className="squat-chart-title">최근 {n}세션 정상 비율 추이</div>
      <div className="squat-chart-sub">날짜별로 정상 자세 비율을 비교해요</div>
      <svg viewBox={`0 0 ${width} ${height}`} className="squat-trend-svg" preserveAspectRatio="xMidYMid meet">
        <line x1={padLeft} y1={top} x2={width - padRight} y2={top} stroke="#e5e3dd" strokeWidth="1" />
        <line x1={padLeft} y1={(top + bottom) / 2} x2={width - padRight} y2={(top + bottom) / 2} stroke="#e5e3dd" strokeWidth="1" />
        <line x1={padLeft} y1={bottom} x2={width - padRight} y2={bottom} stroke="#c3c2b7" strokeWidth="1" />
        <text x={padLeft - 6} y={top + 3} textAnchor="end" fontSize="10" fill="#9b9a96">100</text>
        <text x={padLeft - 6} y={(top + bottom) / 2 + 3} textAnchor="end" fontSize="10" fill="#9b9a96">50</text>
        <text x={padLeft - 6} y={bottom + 3} textAnchor="end" fontSize="10" fill="#9b9a96">0</text>
        <polyline points={pointsAttr} fill="none" stroke="#da291c" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        {points.map((p, i) => (
          <circle key={i} cx={p.x} cy={p.y} r={i === points.length - 1 ? 5 : 4} fill="#da291c" stroke="#fff" strokeWidth="2" />
        ))}
        {last && (
          <text x={last.x} y={top} textAnchor="middle" fontSize="12" fontWeight="700" fill="#111">
            {Math.round(last.ratio * 100)}%
          </text>
        )}
        {points.map((p, i) => (
          <text key={i} x={p.x} y={height - 6} textAnchor="middle" fontSize="10" fill="#9b9a96">
            {formatShortDate(p.date)}
          </text>
        ))}
      </svg>
    </div>
  )
}

// 스쿼트 반복(렙)마다 정상/이상 판정을 점으로 순서대로 보여준다.
function RepTimeline({ reps }) {
  return (
    <div className="squat-chart-card">
      <div className="squat-chart-title">렙별 판정 타임라인</div>
      <div className="squat-chart-sub">스쿼트 반복마다 어떤 이상이 감지됐는지 확인하세요</div>
      <div className="squat-timeline-legend">
        <span className="squat-legend-item">
          <span className="squat-legend-dot squat-legend-dot-ok" />정상
        </span>
        <span className="squat-legend-item">
          <span className="squat-legend-dot squat-legend-dot-warn" />이상 감지
        </span>
      </div>
      <div className="squat-rep-dots">
        {reps.map((rep, i) => {
          const label = rep.is_normal
            ? `${i + 1}회 · 정상`
            : `${i + 1}회 · ${rep.issues?.map((iss) => PART_LABELS[iss.part] ?? iss.part).join(', ') || '이상'}`
          return (
            <span
              key={i}
              className={`squat-rep-dot ${rep.is_normal ? 'squat-rep-dot-ok' : 'squat-rep-dot-warn'}`}
              title={label}
            />
          )
        })}
      </div>
    </div>
  )
}

// 이번 달 달력에 날짜별 목표 달성 여부(초록 반투명 채움)를 보여준다 — 실시간 코칭 화면의
// 달력 모달(ActiveView)과 리포트 화면(ReportView) 양쪽에서 재사용한다. goalTarget이
// 없으면(마이페이지에서 목표 미설정) 채움 없이 설정해 달라는 안내만 보여준다. 오른쪽에는
// 오늘 누적 리포트를 도넛 그래프로 항상 같이 보여준다(TodayReportGraph).
function SquatGoalCalendar({ dailyStats, goalTarget }) {
  const [monthOffset, setMonthOffset] = useState(0)
  const base = new Date()
  const viewDate = new Date(base.getFullYear(), base.getMonth() + monthOffset, 1)
  const year = viewDate.getFullYear()
  const month = viewDate.getMonth()
  const firstWeekday = new Date(year, month, 1).getDay()
  const daysInMonth = new Date(year, month + 1, 0).getDate()
  const today = todayDateKey()

  const cells = []
  for (let i = 0; i < firstWeekday; i++) cells.push(null)
  for (let d = 1; d <= daysInMonth; d++) cells.push(d)

  const todayStat = dailyStats[today]
  const todayReps = todayStat?.total_reps ?? 0
  const todayGoalMet = goalTarget != null && todayReps >= goalTarget

  return (
    <div className="squat-calendar-row">
      <div className="squat-calendar-card">
        <div className="squat-calendar-header">
          <button type="button" className="squat-calendar-nav" onClick={() => setMonthOffset((m) => m - 1)} aria-label="이전 달">
            ‹
          </button>
          <span className="squat-calendar-month">{year}년 {month + 1}월</span>
          <button type="button" className="squat-calendar-nav" onClick={() => setMonthOffset((m) => m + 1)} aria-label="다음 달">
            ›
          </button>
        </div>

        {goalTarget != null ? (
          <div className="squat-calendar-today-goal">
            오늘 목표 {goalTarget}회 중 <b>{Math.min(todayReps, goalTarget)}회</b>
            {todayGoalMet ? ' · 달성! 🎉' : ` · ${Math.max(goalTarget - todayReps, 0)}회 남았어요`}
          </div>
        ) : (
          <div className="squat-calendar-today-goal squat-calendar-no-goal">
            마이페이지에서 스쿼트 목표 횟수를 설정하면 달성한 날이 표시돼요.
          </div>
        )}

        <div className="squat-calendar-weekdays">
          {['일', '월', '화', '수', '목', '금', '토'].map((w) => (
            <span key={w}>{w}</span>
          ))}
        </div>
        <div className="squat-calendar-grid">
          {cells.map((d, i) => {
            if (d == null) return <span key={i} className="squat-calendar-cell squat-calendar-cell-empty" />
            const dateKey = formatDateKey(new Date(year, month, d))
            const stat = dailyStats[dateKey]
            const met = goalTarget != null && stat != null && stat.total_reps >= goalTarget
            const isToday = dateKey === today
            const title = stat ? `${dateKey} · ${stat.total_reps}회` : dateKey
            return (
              <span
                key={i}
                className={`squat-calendar-cell${met ? ' squat-calendar-cell-met' : ''}${isToday ? ' squat-calendar-cell-today' : ''}`}
                title={title}
              >
                {d}
              </span>
            )
          })}
        </div>
      </div>

      <TodayReportGraph todayStat={todayStat} />
    </div>
  )
}

// 오늘 누적 리포트(총 운동시간/총 횟수/정상 비율/이상 감지)를 도넛 링 + 막대 그래프로
// 보여준다 — 달력 오른쪽에 항상 붙어서 나온다(클릭 없이 바로 보임).
function TodayReportGraph({ todayStat }) {
  const hasData = Boolean(todayStat && todayStat.total_reps > 0)
  const normalReps = hasData ? todayStat.total_reps - todayStat.abnormal_reps : 0
  const normalRatio = hasData ? normalReps / todayStat.total_reps : 0
  const pct = Math.round(normalRatio * 100)
  const isGood = normalRatio >= 0.8
  const ringColor = isGood ? '#2eb872' : '#da291c'
  const ringWash = isGood ? 'rgba(46, 184, 114, 0.16)' : 'rgba(218, 41, 28, 0.14)'
  const r = 30
  const circumference = 2 * Math.PI * r
  const offset = circumference * (1 - normalRatio)
  const normalPct = hasData ? Math.round((normalReps / todayStat.total_reps) * 100) : 0

  return (
    <div className="squat-today-graph-card">
      <div className="squat-today-graph-title">오늘의 리포트</div>
      {hasData ? (
        <>
          <div className="squat-today-graph-donut-row">
            <svg width="72" height="72" viewBox="0 0 72 72">
              <circle cx="36" cy="36" r={r} fill="none" stroke={ringWash} strokeWidth="8" />
              <circle
                cx="36"
                cy="36"
                r={r}
                fill="none"
                stroke={ringColor}
                strokeWidth="8"
                strokeLinecap="round"
                strokeDasharray={circumference}
                strokeDashoffset={offset}
                transform="rotate(-90 36 36)"
              />
              <text x="36" y="41" textAnchor="middle" fontSize="15" fontWeight="700" fill="#111">
                {pct}%
              </text>
            </svg>
            <div className="squat-today-graph-donut-label">
              <div className="squat-today-graph-donut-caption">정상 자세 비율</div>
              <div className="squat-today-graph-sub">
                {formatSessionDuration(todayStat.total_duration_sec)} · {todayStat.total_reps}회
              </div>
            </div>
          </div>
          <div className="squat-today-graph-bar">
            <div className="squat-today-graph-bar-normal" style={{ width: `${normalPct}%` }} />
          </div>
          <div className="squat-today-graph-legend">
            <span>
              <span className="squat-today-graph-dot squat-today-graph-dot-ok" />
              정상 {normalReps}회
            </span>
            <span>
              <span className="squat-today-graph-dot squat-today-graph-dot-warn" />
              이상 {todayStat.abnormal_reps}회
            </span>
          </div>
        </>
      ) : (
        <div className="squat-today-graph-empty">오늘은 아직 운동 기록이 없어요.</div>
      )}
    </div>
  )
}

function ReportView({ session }) {
  const {
    sessionReport,
    sessionHistory,
    repHistory,
    dailyStats,
    squatGoalTarget,
    reportLoading,
    reportError,
    restart,
  } = session

  const hasIssueCounts = sessionReport && Object.keys(sessionReport.issue_counts_by_part ?? {}).length > 0
  const todayStat = dailyStats[todayDateKey()]

  return (
    <div className="squat-card squat-report">
      <h2 className="squat-report-title">오늘의 스쿼트 리포트</h2>

      {reportLoading && <p className="squat-report-loading">리포트를 만들고 있어요...</p>}
      {reportError && <p className="squat-error">{reportError}</p>}

      {sessionReport && (
        <>
          <p className="squat-report-summary">{sessionReport.summary_message}</p>
          <p className="squat-report-line">{sessionReport.recommended_frequency_message}</p>

          <div className="squat-today-row">
            <div className="squat-today-stats">
              <div className="squat-today-stat">
                <div className="squat-today-stat-label">오늘 총 운동시간</div>
                <div className="squat-today-stat-value">{formatSessionDuration(todayStat?.total_duration_sec ?? 0)}</div>
              </div>
              <div className="squat-today-stat">
                <div className="squat-today-stat-label">오늘 총 스쿼트 횟수</div>
                <div className="squat-today-stat-value">
                  {todayStat?.total_reps ?? 0}
                  <span className="unit">회</span>
                </div>
              </div>
              <div className="squat-today-stat">
                <div className="squat-today-stat-label">오늘 이상 자세 감지</div>
                <div className="squat-today-stat-value">
                  {todayStat?.abnormal_reps ?? 0}
                  <span className="unit">회</span>
                </div>
              </div>
            </div>
            <SquatGoalCalendar dailyStats={dailyStats} goalTarget={squatGoalTarget} />
          </div>

          <div className="squat-stats-section-title">스쿼트 분석</div>

          <NormalRatioMeter report={sessionReport} />

          <div className="squat-stat-tile-row">
            <div className="squat-stat-tile">
              <div className="squat-stat-tile-label">총 스쿼트 횟수</div>
              <div className="squat-stat-tile-value">
                {sessionReport.total_reps}
                <span className="unit">회</span>
              </div>
            </div>
            <div className="squat-stat-tile">
              <div className="squat-stat-tile-label">이상 자세 감지</div>
              <div className="squat-stat-tile-value">
                {sessionReport.abnormal_reps}
                <span className="unit">회</span>
              </div>
            </div>
          </div>

          {hasIssueCounts && (
            <IssuePartBarChart counts={sessionReport.issue_counts_by_part} mostFrequent={sessionReport.most_frequent_issue_part} />
          )}

          {sessionHistory.length > 1 && <SessionTrendChart history={sessionHistory} />}

          {repHistory.length > 0 && <RepTimeline reps={repHistory} />}
        </>
      )}

      <button className="squat-btn squat-btn-primary" onClick={restart} style={{ marginTop: 16 }}>
        다시 운동하기
      </button>
    </div>
  )
}

function SquatCoachingPage() {
  const session = useSquatCoachingSession()
  const [calendarOpen, setCalendarOpen] = useState(false)

  return (
    <PageShell>
      <div className="page-eyebrow-row">
        <div className="page-index-tag">SQUAT COACHING</div>
      </div>
      <div className="section-head">
        <div className="section-title">실시간 스쿼트 코칭</div>
        <button
          type="button"
          className="squat-calendar-open-btn"
          onClick={() => setCalendarOpen(true)}
          aria-label="운동 달력 보기"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
            <line x1="16" y1="2" x2="16" y2="6" />
            <line x1="8" y1="2" x2="8" y2="6" />
            <line x1="3" y1="10" x2="21" y2="10" />
          </svg>
        </button>
      </div>

      <div className="squat-page-body">
        {session.phase === 'idle' && <IdleView onStart={session.start} cameraError={session.cameraError} />}
        {session.phase === 'active' && <ActiveView session={session} />}
        {session.phase === 'report' && <ReportView session={session} />}
      </div>

      {calendarOpen && (
        <div className="modal-backdrop" onClick={() => setCalendarOpen(false)}>
          <div className="modal squat-calendar-modal" onClick={(e) => e.stopPropagation()}>
            <button className="modal-close" onClick={() => setCalendarOpen(false)} aria-label="닫기">
              ×
            </button>
            <div className="modal-title">운동 달력</div>
            <SquatGoalCalendar dailyStats={session.dailyStats} goalTarget={session.squatGoalTarget} />
          </div>
        </div>
      )}
    </PageShell>
  )
}

export default SquatCoachingPage

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
import { Link } from 'react-router-dom'
import PageShell from '../components/PageShell.jsx'
import SquatGoalCalendar from '../components/SquatGoalCalendar.jsx'
import RecentSessionsList from '../components/RecentSessionsList.jsx'
import ExerciseGoalModal from '../components/ExerciseGoalModal.jsx'
import { useSquatCoachingSession } from '../hooks/useSquatCoachingSession.js'
import { PART_LABELS } from '../lib/squatPose.js'
import { todayDateKey } from '../lib/squatDailyStats.js'
import { loadSquatLevel, saveSquatLevel } from '../lib/squatLevelPreference.js'
import { loadSquatSessionHistory } from '../lib/squatSessionHistory.js'
import { loadExerciseGoalState, saveExerciseGoals, getExerciseGoal } from '../lib/exerciseGoals.js'
import { useAuth } from '../lib/auth.js'
import ReportModal from '../components/ReportModal.jsx'
import './squatShared.css'
import './SquatCoachingPage.css'

// (2026-09-08 추가, 같은 날 재수정) level: 'expert' | 'beginner'.
// 실제 판정 로직은 두 모드가 거의 같고(설명은 기존 서 있는 상태 안내, 완료는 기존 세션
// 자동 종료 조건이 그대로 담당), 초심자 모드에서는 마지막 안내 문구만 "반복 횟수" 대신
// "바른 자세 유지"로 바뀌고, ActiveView의 목표 진행 표시가 숨겨진다(아래 ActiveView 참고).
//
// (재수정) 처음엔 세션 시작 전 팝업 모달(SquatLevelModal)로 고르게 했었는데, "모달 대신
// 안내 문구가 처음부터 보이고 버튼 두 개로 바로 전환되게" 요청에 따라 팝업을 없애고 이
// 화면(IdleView)에 알약(pill) 모양 세그먼트 토글 + 선택된 모드 설명 문구를 바로 넣었다.
// 선택은 누르는 즉시 반영되고(onSelectLevel), 값 저장은 그대로 squatLevelPreference.js가
// 담당한다(처음 방문 시 초심자 기본, 숙련자로 한 번 바꾸면 계속 유지).
function IdleView({ onStart, cameraError, level, onSelectLevel }) {
  const isBeginner = level === 'beginner'
  return (
    <div className="squat-card squat-idle">
      <h2 className="squat-idle-title">실시간 스쿼트 코칭을 시작할게요</h2>

      <div className="squat-level-toggle" role="group" aria-label="코칭 모드 선택">
        <button
          type="button"
          className={`squat-level-toggle-btn${isBeginner ? ' is-active' : ''}`}
          onClick={() => onSelectLevel('beginner')}
        >
          초심자
        </button>
        <button
          type="button"
          className={`squat-level-toggle-btn${isBeginner ? '' : ' is-active-expert'}`}
          onClick={() => onSelectLevel('expert')}
        >
          숙련자
        </button>
      </div>
      <p className="squat-level-desc">
        {isBeginner ? (
          <>
            스쿼트 방법을 처음부터 차근차근 안내해드려요.
            <br />
            반복 횟수 대신, 바른 자세를 잠시 유지하면 완료로 안내해드려요.
          </>
        ) : (
          <>
             반복 횟수를 세고 목표 대비 진행 상황을 보여드려요.
            <br />
            측면은 자세 전반을, 정면은 무릎모임만 확인해요.
            <br />
            이상 자세가 감지될 때만 짚어드려요.
          </>
        )}
      </p>

      <ol className="squat-idle-steps">
        <li>휴대폰이나 노트북 카메라를 측면(옆모습)이 보이도록 세워주세요.</li>
        <li>발끝부터 머리까지 화면에 다 들어오게 한 걸음 물러나 주세요.</li>
        <li>시작 버튼을 누르면 카메라 권한을 요청해요.</li>
        <li>스쿼트를 하는 동안 실시간으로 자세를 확인해요.</li>
        <li>자세가 정상인지 아닌지 음성으로 바로바로 안내해드려요.</li>
        {isBeginner ? (
          <li>바른 자세를 목표 시간만큼 유지하면 완료로 안내해드려요. (언제든 "운동 종료" 버튼으로 직접 끝낼 수도 있어요.)</li>
        ) : (
          <li>반복 횟수를 세서 마이페이지 목표 대비 진행 상황을 보여드려요. (언제든 "운동 종료" 버튼으로 직접 끝낼 수도 있어요.)</li>
        )}
      </ol>
      {cameraError && <p className="squat-error">{cameraError}</p>}
      <button className="squat-btn squat-btn-primary" onClick={onStart}>
        카메라 켜고 시작하기
      </button>
    </div>
  )
}

function ActiveView({ session, level }) {
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
    repHistory,
    dailyStats,
    squatGoal,
  } = session

  const isWarmingUp = bufferCount < 3
  // (2026-09-08 추가, 같은 날 목표에 세트 개념이 생기면서 수정) 숙련자 모드 전용 — 오늘
  // 이미 끝낸 세션(=세트) 수(dailyStats.total_sets, 세션 종료 때만 갱신됨)와 지금 진행 중인
  // 세트의 반복 횟수(repHistory, 렙이 끝날 때마다 실시간 갱신됨)를 보여준다. 초심자
  // 모드에서는 렙/세트 개념 자체를 강조하지 않기로 했으므로(설계 논의 참고) 렌더링하지 않는다.
  const isBeginner = level === 'beginner'
  const todaySets = dailyStats[todayDateKey()]?.total_sets ?? 0
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

        {!isBeginner && !isFront && (
          <p className="squat-progress-note squat-goal-live">
            {squatGoal ? (
              <>
                오늘 <b>{Math.min(todaySets, squatGoal.targetSets)}</b>/{squatGoal.targetSets}세트 완료
                {todaySets >= squatGoal.targetSets ? ' · 목표 달성! 🎉' : ''}
                {' · '}이번 세트 <b>{repHistory.length}</b>/{squatGoal.targetReps}회
              </>
            ) : (
              <>이번 세트 <b>{repHistory.length}</b>회 진행 중 · 마이페이지에서 목표를 설정하면 진행률이 표시돼요</>
            )}
          </p>
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

  // (2026-09-09 수정) "스쿼트 분석" 제목을 이 박스 바깥(ReportView)에 따로 두지 않고
  // 도넛 그래프와 같은 박스 안 맨 위로 옮겼다. 정상/이상 판정 횟수는 박스 하단에 전체
  // 너비 줄로 두면 박스가 쓸데없이 길어져서, 도넛 아래 비어 있던 자리(.squat-meter-ring-sub)
  // 로 옮겼다 — 새 자리를 차지하지 않는다.
  return (
    <div className="squat-meter-card">
      <div className="squat-meter-section-title">스쿼트 분석</div>
      <div className="squat-meter-row">
        <div className="squat-meter-ring-col">
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
          <div className="squat-meter-ring-sub">
            <div className="squat-meter-ring-sub-title">정상/이상 동작 횟수</div>
            <div className="squat-meter-ring-sub-counts">
              <span className="squat-legend-item">
                <span className="squat-legend-dot squat-legend-dot-ok" />정상 {report.normal_reps}회
              </span>
              <span className="squat-legend-item">
                <span className="squat-legend-dot squat-legend-dot-warn" />이상 {report.abnormal_reps}회
              </span>
            </div>
          </div>
        </div>
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
    </div>
  )
}

// 부위별 이상 발생 빈도를 가로 막대그래프로 보여준다.
// (2026-09-09 수정) 최댓값 막대가 트랙 100%까지 꽉 차면 그 옆 "N회" 숫자가 카드 밖으로
// 밀려나 두 줄로 깨졌다 — 최댓값이라도 78%까지만 채우고 나머지는 여백으로 남겨 숫자가
// 항상 한 줄로 들어갈 공간을 확보한다.
const ISSUE_BAR_MAX_FILL_PCT = 78
function IssuePartBarChart({ counts, mostFrequent }) {
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1])
  const max = entries.length > 0 ? entries[0][1] : 1
  return (
    <div className="squat-chart-card">
      <div className="squat-chart-title">부위별 이상 발생 빈도</div>
      {mostFrequent && (
        <div className="squat-chart-sub">가장 빈번한 이상 부위: {PART_LABELS[mostFrequent] ?? mostFrequent}</div>
      )}
      {entries.map(([part, count]) => {
        const fillPct = Math.round((count / max) * ISSUE_BAR_MAX_FILL_PCT)
        return (
          <div key={part} className="squat-bar-row">
            <div className="squat-bar-label">{PART_LABELS[part] ?? part}</div>
            <div className="squat-bar-track">
              <div className="squat-bar-fill" style={{ width: `${fillPct}%` }} />
              <div className="squat-bar-value" style={{ left: `calc(${fillPct}% + 8px)` }}>
                {count}회
              </div>
            </div>
          </div>
        )
      })}
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

// (2026-09-09 재구성) 상단 통계 3칸을 "오늘 누적"(dailyStats)이 아니라 "이번 세션"
// (sessionReport) 값으로 통일하고, "스쿼트 분석"을 좌(자세 분석: 게이지+막대그래프+
// 타임라인)/우(달력+추이 그래프) 2단 구성으로 바꿨다 — 목업 검토 결과 아래쪽에 따로 있던
// "총 스쿼트 횟수/이상 자세 감지" 통계 칸은 위 3칸과 값이 겹쳐서(같은 세션 기준) 없앴다.
function ReportView({ session }) {
  const {
    sessionReport,
    sessionHistory,
    repHistory,
    dailyStats,
    squatGoal,
    reportLoading,
    reportError,
    restart,
  } = session

  const hasIssueCounts = sessionReport && Object.keys(sessionReport.issue_counts_by_part ?? {}).length > 0

  const { submitReport } = useAuth()
  const [reportOpen, setReportOpen] = useState(false)

  // 실시간 세션은 서버에 좌표만 보내고 영상 자체는 클라이언트에 남지 않으므로, 신고 원본은
  // "이 세션의 렙별 판정 시계열(repHistory) + 최종 리포트"를 JSON으로 묶어 보낸다 -
  // 8/27 addendum에서 말한 "원본 데이터(영상/좌표 시계열)" 중 좌표 시계열 쪽.
  const handleReportSubmit = async ({ reasonCategory, reasonDetail }) => {
    const payload = { sessionReport, repHistory }
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
    await submitReport({
      sourceType: 'SESSION',
      sourceId: `session-report-${Date.now()}`,
      file: blob,
      fileName: 'session-report.json',
      reasonCategory,
      reasonDetail,
      judgmentSnapshot: sessionReport,
    })
  }

  // (2026-09-09 재구성) 달력이 제목 줄과 같은 높이가 아니라 "스쿼트 분석" 박스와 같은
  // 줄에서 시작해야 한다는 피드백에 따라, [제목+오늘 점수 / 통계 3칸] 헤더 줄과 설명
  // 문구를 왼쪽 칼럼 밖으로 빼서 카드 전체 폭을 쓰는 줄로 만들었다 — 그 아래부터 시작하는
  // 2단 그리드(왼쪽: 스쿼트 분석·막대그래프·타임라인 / 오른쪽: 달력·추이그래프·버튼)에서
  // 달력이 자연스럽게 "스쿼트 분석" 박스와 같은 줄에서 시작한다. 통계 3칸은 이제 카드
  // 전체 폭 기준으로 오른쪽 끝까지 밀린다. 리포트가 아직 없을 때(로딩/에러)는 나눌 내용이
  // 없으니 제목만 단순하게 보여준다.
  if (!sessionReport) {
    return (
      <div className="squat-card squat-report">
        <h2 className="squat-report-title">오늘의 스쿼트 리포트</h2>
        {reportLoading && <p className="squat-report-loading">리포트를 만들고 있어요...</p>}
        {reportError && <p className="squat-error">{reportError}</p>}
      </div>
    )
  }

  return (
    <div className="squat-card squat-report">
      <div className="squat-report-header-row">
        <div className="squat-report-title-row">
          <h2 className="squat-report-title">오늘의 스쿼트 리포트</h2>
          <div className="squat-report-score" title="오늘 운동 점수">
            <span className="squat-report-score-value">{sessionReport.score}</span>
            <span className="squat-report-score-unit">점</span>
          </div>
        </div>
        <div className="squat-today-stats squat-today-stats-compact">
          <div className="squat-today-stat">
            <div className="squat-today-stat-label">총 운동시간</div>
            <div className="squat-today-stat-value">{formatSessionDuration(sessionReport.session_duration_sec)}</div>
          </div>
          <div className="squat-today-stat">
            <div className="squat-today-stat-label">총 스쿼트 횟수</div>
            <div className="squat-today-stat-value">
              {sessionReport.total_reps}
              <span className="unit">회</span>
            </div>
          </div>
          <div className="squat-today-stat">
            <div className="squat-today-stat-label">이상 자세 감지</div>
            <div className="squat-today-stat-value">
              {sessionReport.abnormal_reps}
              <span className="unit">회</span>
            </div>
          </div>
        </div>
      </div>

      <p className="squat-report-summary">{sessionReport.summary_message}</p>
      <p className="squat-report-line">{sessionReport.recommended_frequency_message}</p>

      <div className="squat-analysis-grid">
        <div className="squat-analysis-col">
          <NormalRatioMeter report={sessionReport} />
          {hasIssueCounts && (
            <IssuePartBarChart counts={sessionReport.issue_counts_by_part} mostFrequent={sessionReport.most_frequent_issue_part} />
          )}
          {repHistory.length > 0 && <RepTimeline reps={repHistory} />}
        </div>

        <div className="squat-analysis-col squat-analysis-side">
          <SquatGoalCalendar dailyStats={dailyStats} goal={squatGoal} />
          {sessionHistory.length > 1 && <SessionTrendChart history={sessionHistory} />}
          {/* (2026-09-09) 왼쪽 칼럼이 오른쪽보다 길어서(막대그래프+타임라인까지 있음) 오른쪽
              칼럼(달력+추이그래프) 아래로 남는 세로 공간이 생긴다 — 두 버튼을 그 공간의
              한가운데(위/아래 margin:auto)로 오게 했다. */}
          <div className="squat-report-actions">
            <Link to="/exercises-history" className="squat-btn squat-btn-outline squat-report-history-btn">
              지난 운동 기록 보기
            </Link>
            <button type="button" className="squat-btn squat-btn-outline" onClick={() => setReportOpen(true)}>
              이 판정 신고하기
            </button>
            <button className="squat-btn squat-btn-primary squat-report-restart-btn" onClick={restart}>
              다시 운동하기
            </button>
          </div>

          {reportOpen && <ReportModal onClose={() => setReportOpen(false)} onSubmit={handleReportSubmit} />}
        </div>
      </div>
    </div>
  )
}

function SquatCoachingPage() {
  const session = useSquatCoachingSession()
  const [calendarOpen, setCalendarOpen] = useState(false)
  // (2026-09-09 추가) "카메라 켜고 시작하기"를 눌렀을 때 목표(마이페이지에서 설정하는
  // 하루 목표 횟수·세트)가 아직 한 번도 설정 안 돼 있으면(loadExerciseGoalState().configured
  // === false — 마이페이지가 "운동 목표를 설정해주세요" 안내를 띄우는 것과 같은 기준),
  // 카메라를 바로 켜는 대신 목표 설정 모달을 띄운다. 저장하면(같은 localStorage를 쓰므로
  // 마이페이지에도 그대로 반영됨) 모달을 닫고 이어서 카메라를 켠다 — 다시 버튼을 누르지
  // 않아도 되게. 이미 목표가 설정돼 있으면 지금처럼 바로 시작한다.
  const [goalModalOpen, setGoalModalOpen] = useState(false)
  const handleStartClick = () => {
    if (!loadExerciseGoalState().configured) {
      setGoalModalOpen(true)
      return
    }
    session.start()
  }
  const handleSaveGoalAndStart = (goals) => {
    saveExerciseGoals(goals)
    session.setSquatGoal(getExerciseGoal('squat'))
    session.start()
  }
  // (2026-09-08 추가, 같은 날 두 차례 수정) 초심자/숙련자 모드. 판정 로직 자체는 두 모드가
  // 거의 같고(IdleView/ActiveView 주석 참고), 반복 횟수/목표 진행 표시만 숙련자 모드
  // 전용으로 갈린다.
  //
  // 기본값은 하드코딩된 'expert'가 아니라 localStorage에 저장된 값 — 처음 방문(저장된 값
  // 없음)이면 초심자로 시작하고, 숙련자로 한 번이라도 바꾸면 그 다음부터는 계속 숙련자로
  // 시작한다(squatLevelPreference.js 참고). 처음엔 세션 시작 전 팝업 모달로 고르게
  // 했었으나, 팝업 없이 IdleView에 바로 보이는 토글로 바꿨다(IdleView 주석 참고) — 그래서
  // 여기 남은 건 값 하나(level)와 토글이 누르는 즉시 부르는 저장 핸들러뿐이다.
  const [level, setLevel] = useState(() => loadSquatLevel())
  const handleSelectLevel = (next) => {
    setLevel(next)
    saveSquatLevel(next)
  }

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
        {session.phase === 'idle' && (
          <IdleView
            onStart={handleStartClick}
            cameraError={session.cameraError}
            level={level}
            onSelectLevel={handleSelectLevel}
          />
        )}
        {session.phase === 'active' && <ActiveView session={session} level={level} />}
        {session.phase === 'report' && <ReportView session={session} />}
      </div>

      {goalModalOpen && (
        <ExerciseGoalModal
          goals={loadExerciseGoalState().goals}
          onClose={() => setGoalModalOpen(false)}
          onSave={handleSaveGoalAndStart}
        />
      )}

      {calendarOpen && (
        <div className="modal-backdrop" onClick={() => setCalendarOpen(false)}>
          <div className="modal squat-calendar-modal squat-calendar-modal-wide" onClick={(e) => e.stopPropagation()}>
            <button className="modal-close" onClick={() => setCalendarOpen(false)} aria-label="닫기">
              ×
            </button>
            <div className="modal-title">운동 달력</div>
            {/* (2026-09-09 재구성) 달력 옆에 있던 "오늘의 리포트" 도넛 대신 최근 세션
                리스트를 보여주고, "더보기"로 운동 기록 페이지(/exercises-history)로
                이동한다 — 그 세션의 상세(자세 분석 등)는 거기서 날짜/세션을 골라 본다. */}
            <div className="squat-calendar-modal-body squat-calendar-row">
              <SquatGoalCalendar dailyStats={session.dailyStats} goal={session.squatGoal} />
              <RecentSessionsList sessions={[...loadSquatSessionHistory()].reverse()} limit={6} moreTo="/exercises-history" />
            </div>
          </div>
        </div>
      )}
    </PageShell>
  )
}

export default SquatCoachingPage

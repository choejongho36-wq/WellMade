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

import PageShell from '../components/PageShell.jsx'
import { useSquatCoachingSession } from '../hooks/useSquatCoachingSession.js'
import { PART_LABELS } from '../lib/squatPose.js'
import './squatShared.css'
import './SquatCoachingPage.css'

function IdleView({ onStart, cameraError }) {
  return (
    <div className="squat-card squat-idle">
      <div className="squat-idle-icon">🏋️</div>
      <h2 className="squat-idle-title">실시간 스쿼트 코칭을 시작할게요</h2>
      <p className="squat-idle-desc">
        휴대폰이나 노트북 카메라를 측면(옆모습)이 보이도록 세워두고, 발끝부터 머리까지
        화면에 들어오게 한 걸음 물러나 주세요. 시작하면 카메라 권한을 요청하고, 스쿼트를
        하는 동안 실시간으로 자세를 확인해서 음성으로 안내해드려요.
      </p>
      <ul className="squat-idle-tips">
        <li>바른 자세를 목표 시간만큼 유지하면 자동으로 세션이 끝나요.</li>
        <li>언제든 "운동 종료" 버튼으로 직접 끝낼 수 있어요.</li>
      </ul>
      {cameraError && <p className="squat-error">{cameraError}</p>}
      <button className="squat-btn squat-btn-primary" onClick={onStart}>
        카메라 켜고 시작하기
      </button>
    </div>
  )
}

function ActiveView({ session }) {
  const { videoRef, canvasRef, judgeResult, judgeError, bufferCount, bufferMax, endCheck, ttsEnabled, setTtsEnabled, endSession } =
    session

  const isWarmingUp = bufferCount < 3
  const feedbackText = judgeError
    ? judgeError
    : isWarmingUp
      ? '자세를 인식하고 있어요...'
      : judgeResult
        ? judgeResult.is_normal
          ? '좋아요, 지금 자세를 유지하세요'
          : (judgeResult.issues?.[0]?.message ?? '자세를 확인해주세요')
        : '자세를 인식하고 있어요...'

  const feedbackState = judgeError ? 'error' : isWarmingUp || !judgeResult ? 'warming' : judgeResult.is_normal ? 'ok' : 'warn'

  return (
    <div className="squat-active">
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
  )
}

function ReportView({ session }) {
  const { sessionReport, reportLoading, reportError, restart } = session

  return (
    <div className="squat-card squat-report">
      <h2 className="squat-report-title">오늘의 스쿼트 리포트</h2>

      {reportLoading && <p className="squat-report-loading">리포트를 만들고 있어요...</p>}
      {reportError && <p className="squat-error">{reportError}</p>}

      {sessionReport && (
        <>
          <div className="squat-report-stat-row">
            <div className="squat-report-stat">
              <div className="squat-report-stat-value">{Math.round(sessionReport.normal_ratio * 100)}%</div>
              <div className="squat-report-stat-label">정상 자세 비율</div>
            </div>
            {sessionReport.avg_deviation_deg != null && (
              <div className="squat-report-stat">
                <div className="squat-report-stat-value">{sessionReport.avg_deviation_deg.toFixed(1)}°</div>
                <div className="squat-report-stat-label">평균 편차</div>
              </div>
            )}
            {sessionReport.improvement_vs_previous_pct != null && (
              <div className="squat-report-stat">
                <div className="squat-report-stat-value">
                  {sessionReport.improvement_vs_previous_pct > 0 ? '+' : ''}
                  {sessionReport.improvement_vs_previous_pct.toFixed(1)}%p
                </div>
                <div className="squat-report-stat-label">지난 세션 대비</div>
              </div>
            )}
          </div>

          {sessionReport.most_frequent_issue_part && (
            <p className="squat-report-line">
              가장 자주 감지된 부위: <b>{PART_LABELS[sessionReport.most_frequent_issue_part] ?? sessionReport.most_frequent_issue_part}</b>
            </p>
          )}

          <p className="squat-report-summary">{sessionReport.summary_message}</p>
          <p className="squat-report-line">{sessionReport.recommended_frequency_message}</p>
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

  return (
    <PageShell>
      <div className="page-eyebrow-row">
        <div className="page-index-tag">SQUAT COACHING</div>
      </div>
      <div className="section-head">
        <div className="section-title">실시간 스쿼트 코칭</div>
      </div>

      {session.phase === 'idle' && <IdleView onStart={session.start} cameraError={session.cameraError} />}
      {session.phase === 'active' && <ActiveView session={session} />}
      {session.phase === 'report' && <ReportView session={session} />}
    </PageShell>
  )
}

export default SquatCoachingPage

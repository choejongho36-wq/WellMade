/**
 * 사진 코칭(②-A) 페이지 — 서비스 흐름도의 "② 코칭 모드 선택"에서 "사진 코칭"을 고르면
 * 오는 화면. 2026-09-02 시안 반영: 상단에 운동 선택 드롭다운 + "운동방법" 모달 버튼을 두고,
 * 본문은 좌측 "사진 미리보기" / 우측 "분석 결과" 2단 레이아웃으로 바꿨다(웹캠 실시간 미리보기
 * 대신 사진 업로드 방식).
 *
 * 정지 자세 1차 판정(AI-03)은 팀원 서비스가 담당하기로 하고 삭제됐지만(MlTestPage.jsx
 * 상단 docstring 참고), AI-06(실시간 코칭 판정)은 그대로 남아 있다. 사진 한 장의 값을
 * 타임스탬프만 다르게 3프레임으로 복제해 보내면 AI-06이 "정지" 상태로 인식해 실제 임계값
 * 비교를 그대로 적용해준다 — hooks/usePhotoCoachingSession.js 참고.
 *
 * "분석 결과" 패널의 지표 정의(ANALYSIS_METRICS)는 lib/squatPose.js에 있다 — 왜 원래
 * 디자인 시안의 수치(무릎 각도 권장범위 85~100°, 등 기울기, 좌우 균형 등)를 그대로 쓰지
 * 않고 실제 서버 임곗값 기준으로 다시 짰는지는 그 파일 주석(2026-09-02 검수) 참고.
 */

import { useState } from 'react'
import { Link } from 'react-router-dom'
import PageShell from '../components/PageShell.jsx'
import ExerciseGuideModal from '../components/ExerciseGuideModal.jsx'
import ExerciseSelectDropdown from '../components/ExerciseSelectDropdown.jsx'
import { usePhotoCoachingSession } from '../hooks/usePhotoCoachingSession.js'
import { ANALYSIS_METRICS, PART_LABELS } from '../lib/squatPose.js'
import './squatShared.css'
import './PhotoCoachingPage.css'

function MetricBar({ value, scale, ok }) {
  const [scaleMin, scaleMax] = scale
  const [okMin, okMax] = ok
  const clampPct = (v) => Math.max(0, Math.min(100, ((v - scaleMin) / (scaleMax - scaleMin)) * 100))
  const okStart = clampPct(okMin)
  const okEnd = clampPct(okMax)
  const markerPct = clampPct(value)
  return (
    <div className="metric-bar">
      <div className="metric-bar-ok" style={{ left: `${okStart}%`, width: `${okEnd - okStart}%` }} />
      <div className="metric-bar-marker" style={{ left: `${markerPct}%` }} />
    </div>
  )
}

function AnalysisMetricRow({ metric, metrics, judgeResult, isDeepHold }) {
  const value = metrics[metric.field]
  const issue = judgeResult?.issues?.find((it) => it.part === metric.part)
  let status = 'ok'
  let statusLabel = '정상'
  let note = ''
  if (metric.gated && !isDeepHold) {
    status = 'pending'
    statusLabel = '판정 보류'
    note = '더 깊이 앉은 사진이어야 이 항목을 판정할 수 있어요.'
  } else if (issue) {
    status = 'warn'
    statusLabel = '주의'
    note = issue.message
  }

  return (
    <div className={`metric-row metric-${status}`}>
      <div className="metric-row-top">
        <span className="metric-label">{metric.label}</span>
        <span className="metric-value">
          {value.toFixed(1)}
          {metric.unit}
        </span>
        <span className={`metric-badge metric-badge-${status}`}>{statusLabel}</span>
      </div>
      <MetricBar value={value} scale={metric.scale} ok={metric.ok} />
      <p className="metric-note">{note || metric.rangeText}</p>
    </div>
  )
}

function AnalysisPanel({ session }) {
  const { phase, poseError, judgeResult, judgeError, metrics, isDeepHold } = session

  if (phase === 'idle') {
    return (
      <div className="analysis-empty">
        사진을 업로드하면 무릎·엉덩이 각도 등 분석 결과가 이 자리에 표시돼요.
      </div>
    )
  }
  if (phase === 'analyzing') {
    return <div className="analysis-empty">AI가 자세를 분석하고 있어요...</div>
  }
  if (poseError) {
    return <p className="squat-error">{poseError}</p>
  }

  const knownParts = new Set(ANALYSIS_METRICS.map((m) => m.part))
  const extraIssues = judgeResult?.issues?.filter((it) => !knownParts.has(it.part)) ?? []

  return (
    <div>
      {judgeResult && (
        <div className="analysis-summary">
          <span className={judgeResult.is_normal ? 'photo-ok' : 'photo-warn'}>
            {judgeResult.is_normal ? '전체적으로 정상 범위예요' : '점검이 필요한 항목이 있어요'}
          </span>
          <span className="analysis-confidence">신뢰도 {Math.round(judgeResult.confidence * 100)}%</span>
        </div>
      )}
      {judgeError && <p className="squat-error">{judgeError}</p>}

      {metrics && (
        <div className="metric-list">
          {ANALYSIS_METRICS.map((metric) => (
            <AnalysisMetricRow
              key={metric.part}
              metric={metric}
              metrics={metrics}
              judgeResult={judgeResult}
              isDeepHold={isDeepHold}
            />
          ))}
        </div>
      )}

      {extraIssues.length > 0 && (
        <div className="photo-issue-list">
          {extraIssues.map((issue, i) => (
            <div key={i} className="squat-issue-row">
              · [{PART_LABELS[issue.part] ?? issue.part}] {issue.message}
            </div>
          ))}
        </div>
      )}

      <p className="analysis-scope-note">
        무릎 모임 · 좌우 비대칭은 정면 촬영이 있어야 계산돼요. 등 굽음은 온보딩 자세
        캘리브레이션이 있어야 판정돼요. 이 사진 코칭(측면 사진 한 장)에서는 두 항목 모두
        표시하지 않아요.
      </p>
    </div>
  )
}

function PhotoPreviewPanel({ session }) {
  const { phase, fileName, photoUrl, avgVisibility } = session

  return (
    <div className="preview-frame">
      {phase === 'idle' && (
        <button type="button" className="preview-placeholder" onClick={session.openFilePicker}>
          <span className="preview-placeholder-icon">📷</span>
          사진을 업로드해주세요
        </button>
      )}
      {phase === 'analyzing' && <div className="preview-placeholder preview-loading">분석 중...</div>}
      {phase === 'result' && photoUrl && (
        <>
          <img src={photoUrl} alt="업로드한 스쿼트 자세" className="preview-img" />
          {avgVisibility != null && (
            <div className="preview-legend">
              <span>
                <i className="legend-dot legend-dot-left" />왼쪽 관절
              </span>
              <span>
                <i className="legend-dot legend-dot-right" />오른쪽 관절
              </span>
              <span>좌표 33개 · 신뢰도 {Math.round(avgVisibility * 100)}%</span>
            </div>
          )}
        </>
      )}
      {fileName && <p className="preview-filename">{fileName}</p>}
    </div>
  )
}

function PhotoCoachingPage() {
  const session = usePhotoCoachingSession()
  const [guideOpen, setGuideOpen] = useState(false)

  return (
    <PageShell>
      <div className="page-eyebrow-row">
        <div className="page-index-tag">PHOTO COACHING</div>
        <div className="photo-header-actions">
          <ExerciseSelectDropdown value="squat" />
          <button type="button" className="squat-btn squat-btn-outline photo-guide-btn" onClick={() => setGuideOpen(true)}>
            운동방법
          </button>
        </div>
      </div>

      <div className="section-head">
        <div className="section-title">사진 코칭</div>
      </div>

      <div className="photo-coaching-grid">
        <div className="squat-card photo-panel">
          <div className="photo-panel-head">사진 미리보기</div>
          <PhotoPreviewPanel session={session} />

          <div className="photo-warning-box">
            <b>업로드 전 확인해 주세요.</b>
            <ul>
              <li>전신이 옆모습(측면)으로 잘 보이는 사진을 올려주세요.</li>
              <li>사진이 흐리거나 신체 일부가 가려지면 분석이 부정확하거나 실패할 수 있어요.</li>
              <li>이 분석 결과는 참고용이에요. 통증이 있다면 무리하지 말고 전문가와 상담해주세요.</li>
            </ul>
          </div>

          {session.fileError && <p className="squat-error">{session.fileError}</p>}

          <input
            ref={session.fileInputRef}
            type="file"
            accept="image/jpeg,image/png"
            className="photo-file-input"
            onChange={session.onFileInputChange}
          />
          <button type="button" className="squat-btn squat-btn-primary" onClick={session.openFilePicker}>
            {session.phase === 'result' ? '다른 사진 업로드' : '사진 업로드'}
          </button>
          <p className="photo-upload-caption">JPG · PNG · 최대 10MB</p>
        </div>

        <div className="squat-card photo-panel">
          <div className="photo-panel-head">분석 결과</div>
          <AnalysisPanel session={session} />
        </div>
      </div>

      <p className="photo-back-link">
        <Link to="/squat">← 코칭 모드 다시 고르기</Link>
      </p>

      {guideOpen && <ExerciseGuideModal onClose={() => setGuideOpen(false)} />}
    </PageShell>
  )
}

export default PhotoCoachingPage

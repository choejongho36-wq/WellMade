/**
 * 정지 자세 분석 페이지 (/posture).
 *
 * 팀의 사진 코칭 페이지(/exercises/photo)는 **운동 동작**(스쿼트)을 다루고,
 * 이 페이지는 **서 있는 정지 자세**를 다룬다. 측정하는 값도 다르다:
 *   정면 — 어깨·골반 좌우 기울기
 *   측면 — 전방머리자세, 라운드숄더
 *
 * 레이아웃과 스타일은 팀 PhotoCoachingPage의 클래스를 그대로 재사용한다
 * (squat-card, photo-panel, preview-frame, section-head 등). 같은 서비스
 * 안의 두 페이지가 서로 다른 모양이면 사용자가 어색해하고, 팀이 스타일을
 * 손볼 때 우리 페이지만 뒤처진다. 우리 전용 스타일(게이지 등)만
 * PosturePage.css 에 posture- 접두사로 추가한다.
 *
 * 사진은 서버로 보내지 않는다. 브라우저에서 MediaPipe로 좌표만 뽑아
 * posture-ai로 전송한다 — 신체 사진이 기기를 벗어나지 않는다.
 */

import { useState } from 'react'
import PageShell from '../components/PageShell.jsx'
import Modal from '../components/Modal.jsx'
import { usePostureSession } from '../hooks/usePostureSession.js'
import './squatShared.css'
import './PhotoCoachingPage.css'
import './PosturePage.css'

const VIEWS = [
  { key: 'side', label: '측면' },
  { key: 'front', label: '정면' },
]

const VERDICT_CLASS = {
  정상: 'posture-verdict-normal',
  경미: 'posture-verdict-mild',
  주의: 'posture-verdict-warn',
}

/**
 * 지표별 3구간 정의.
 *
 * 눈금(숫자)을 그리지 않는 이유:
 *   forward_head 구간(15/25도)은 임상 확립 기준이 없는 잠정값이고,
 *   round_shoulder는 C7을 어깨-골반 좌표로 근사해 계산한 값이라 정밀도가
 *   낮다. 눈금을 그리면 근거가 약한 숫자를 정확한 것처럼 보이게 만든다 —
 *   이 프로젝트가 문서 전반에서 "정량 수치보다 정성 경향"을 원칙으로
 *   삼아온 이유다. 구간은 색으로만 구분하고 마커로 "어디쯤인지"만 보여준다.
 *
 * inverted: round_shoulder는 값이 **클수록** 정상이다(견봉-C7 선이 수직에
 *   가까울수록 어깨가 안 말린 상태). 나머지는 절댓값이 작을수록 정상이라
 *   방향이 반대다.
 */
const METRIC_BANDS = {
  shoulder: { normal: 5, mild: 15, max: 25, inverted: false },
  pelvis: { normal: 5, mild: 15, max: 25, inverted: false },
  forward_head: { normal: 15, mild: 25, max: 45, inverted: false },
  round_shoulder: { normal: 52, mild: 45, max: 90, inverted: true },
}

/** 값이 막대의 몇 % 지점에 오는지(0~100). 막대는 왼쪽이 정상, 오른쪽이 주의다. */
function markerPercent(value, band) {
  if (band.inverted) {
    const clamped = Math.min(Math.max(value, 0), band.max)
    return ((band.max - clamped) / band.max) * 100
  }
  const clamped = Math.min(Math.abs(value), band.max)
  return (clamped / band.max) * 100
}

/** 각 구간이 막대에서 차지하는 폭(%) */
function bandWidths(band) {
  if (band.inverted) {
    return {
      normal: ((band.max - band.normal) / band.max) * 100,
      mild: ((band.normal - band.mild) / band.max) * 100,
      warn: (band.mild / band.max) * 100,
    }
  }
  return {
    normal: (band.normal / band.max) * 100,
    mild: ((band.mild - band.normal) / band.max) * 100,
    warn: ((band.max - band.mild) / band.max) * 100,
  }
}

/**
 * 촬영 전 안내 모달.
 *
 * 팀 PhotoCoachingPage의 UploadNoticeModal과 같은 패턴 — 공용 Modal.jsx +
 * closeOnBackdropClick(안내성 모달) + 초깃값 true(페이지 진입 시 자동 열림).
 *
 * 안내 항목은 posture-ai의 실제 검증 조건과 맞췄다. "몸이 완전히 옆을
 * 향하게"는 quality.py의 MAX_SIDE_SHOULDER_X / MIN_Z_SEPARATION 검사가
 * 실제로 걸러내는 조건이다. 검증에서 안 보는 항목(배경, 카메라 높이)은
 * 넣지 않았다 — 지켜도 결과가 달라지지 않는 안내는 읽는 부담만 준다.
 */
function CaptureNoticeModal({ onClose }) {
  return (
    <Modal onClose={onClose} className="upload-notice-modal" closeOnBackdropClick>
      <div className="modal-title">촬영 전 확인해 주세요</div>
      <ul className="upload-notice-list">
        <li>밝은 곳에서 촬영해 주세요.</li>
        <li>머리부터 발끝까지 전신이 나오도록 촬영해 주세요.</li>
        <li>몸에 붙지 않는 헐렁한 옷은 관절 위치 인식을 어렵게 합니다.</li>
        <li>
          <strong>측면</strong>은 몸이 완전히 옆을 향하게 서 주세요. 비스듬하면
          목·어깨 각도가 실제와 다르게 계산됩니다.
        </li>
        <li>
          <strong>정면</strong>은 어깨와 골반이 카메라를 정면으로 향하게 서 주세요.
        </li>
        <li>이 분석은 참고용이며 의료 진단을 대체하지 않습니다.</li>
      </ul>
    </Modal>
  )
}

/** 사진 업로드 슬롯. 팀 PhotoSlotPanel과 같은 클래스를 쓴다. */
function PhotoSlot({ session, label }) {
  return (
    <div className="squat-card photo-panel photo-slot-panel">
      <div className="photo-panel-head">
        {label}
        <span className="photo-req-badge">필수</span>
      </div>

      <div className="preview-frame">
        <div className="preview-photo-box">
          {session.phase === 'idle' && (
            <button type="button" className="preview-placeholder" onClick={session.openFilePicker}>
              <span className="preview-placeholder-icon">📷</span>
              여기를 눌러 {label} 사진을 업로드해주세요
              <span className="preview-placeholder-hint">JPG · PNG · 최대 10MB</span>
            </button>
          )}

          {session.phase === 'detecting' && (
            <div className="preview-placeholder preview-loading">처리 중...</div>
          )}

          {session.phase === 'error' && (
            <button type="button" className="preview-placeholder" onClick={session.openFilePicker}>
              <span className="preview-placeholder-icon">⚠️</span>
              {session.fileError || '다시 시도해주세요'}
            </button>
          )}

          {session.phase === 'ready' && session.photoUrl && (
            <>
              <img className="posture-preview-img" src={session.photoUrl} alt={`업로드한 ${label} 자세`} />
              <button
                type="button"
                className="photo-delete-btn"
                onClick={session.reset}
                aria-label={`${label} 사진 삭제`}
              >
                ✕
              </button>
            </>
          )}
        </div>

        {session.phase === 'ready' && session.avgVisibility != null && (
          <div className="preview-legend">
            <span>
              관절 인식 신뢰도 {Math.round(session.avgVisibility * 100)}%
              {session.fileName && ` · ${session.fileName}`}
            </span>
          </div>
        )}
        {session.phase !== 'ready' && session.fileName && (
          <p className="preview-filename">{session.fileName}</p>
        )}
      </div>

      {session.fileError && session.phase !== 'error' && (
        <p className="squat-error">{session.fileError}</p>
      )}

      <input
        ref={session.fileInputRef}
        type="file"
        accept="image/jpeg,image/png"
        onChange={session.onFileInputChange}
        hidden
      />
    </div>
  )
}

function MetricRow({ title, metricKey, metric }) {
  if (!metric) return null

  const band = METRIC_BANDS[metricKey]
  const widths = band ? bandWidths(band) : null
  const percent = band ? markerPercent(metric.angle_deg, band) : null

  return (
    <div className="posture-metric-row">
      <div className="posture-metric-head">
        <span className="posture-metric-title">{title}</span>
        <span className={`posture-verdict ${VERDICT_CLASS[metric.verdict] || ''}`}>
          {metric.verdict}
        </span>
      </div>

      {band && (
        <div className="posture-gauge">
          <div className="posture-gauge-bar">
            <span className="posture-band posture-band-normal" style={{ width: `${widths.normal}%` }} />
            <span className="posture-band posture-band-mild" style={{ width: `${widths.mild}%` }} />
            <span className="posture-band posture-band-warn" style={{ width: `${widths.warn}%` }} />
            <span className="posture-marker" style={{ left: `${percent}%` }} />
          </div>
          <div className="posture-gauge-labels">
            <span>정상</span>
            <span>경미</span>
            <span>주의</span>
          </div>
        </div>
      )}

      {/* 정확한 수치는 부가 정보로만 작게 둔다 — 위 막대가 주된 표현이다 */}
      <p className="posture-metric-value">측정값 {metric.angle_deg}도</p>
      {metric.note && <p className="posture-metric-note">{metric.note}</p>}
    </div>
  )
}

function AnalysisPanel({ session, view }) {
  if (session.analyzing) {
    return <p className="posture-panel-empty">분석 중이에요...</p>
  }
  if (session.analyzeError) {
    return <p className="squat-error">{session.analyzeError}</p>
  }
  if (!session.result) {
    return (
      <p className="posture-panel-empty">
        사진을 올리고 "분석하기"를 누르면 결과가 이 자리에 표시돼요.
      </p>
    )
  }

  const { result } = session
  const unreliable = !result.reliability.is_reliable

  return (
    <>
      {unreliable && (
        <div className="posture-warning">
          <strong>이 결과는 신뢰하기 어려워요.</strong>
          <ul>
            {result.reliability.issues.map((issue) => (
              <li key={issue}>{issue}</li>
            ))}
          </ul>
        </div>
      )}

      <div className={unreliable ? 'posture-metrics is-dimmed' : 'posture-metrics'}>
        {view === 'side' ? (
          <>
            <MetricRow title="전방머리자세" metricKey="forward_head" metric={result.forward_head} />
            <MetricRow title="라운드숄더" metricKey="round_shoulder" metric={result.round_shoulder} />
          </>
        ) : (
          <>
            <MetricRow title="어깨 좌우 기울기" metricKey="shoulder" metric={result.shoulder} />
            <MetricRow title="골반 좌우 기울기" metricKey="pelvis" metric={result.pelvis} />
          </>
        )}
      </div>

      {result.comment?.text && <p className="posture-comment">{result.comment.text}</p>}
      <p className="posture-disclaimer">{result.disclaimer}</p>
    </>
  )
}

function PosturePage() {
  const [view, setView] = useState('side')
  // 초깃값 true — 이 페이지에 들어올 때마다 자동으로 뜬다(팀 사진 코칭과 동일).
  const [noticeOpen, setNoticeOpen] = useState(true)
  const session = usePostureSession(view)

  const handleViewChange = (key) => {
    if (key === view || session.analyzing) return
    setView(key)
    session.reset()
  }

  return (
    <PageShell>
      <div className="page-eyebrow-row">
        <div className="page-index-tag">POSTURE CHECK</div>
      </div>

      <div className="section-head">
        <div className="section-title">정지 자세 분석</div>
        <div className="photo-analyze-inline">
          <div className="posture-view-tabs">
            {VIEWS.map((v) => (
              <button
                key={v.key}
                type="button"
                className={v.key === view ? 'posture-view-tab is-active' : 'posture-view-tab'}
                onClick={() => handleViewChange(v.key)}
                disabled={session.analyzing}
              >
                {v.label}
              </button>
            ))}
          </div>
          <button
            type="button"
            className="squat-btn squat-btn-primary photo-analyze-btn"
            onClick={session.runAnalysis}
            disabled={!session.canAnalyze}
          >
            {session.analyzing ? '분석 중...' : '분석하기'}
          </button>
          {session.phase !== 'ready' && (
            <p className="photo-analyze-hint">
              {view === 'side' ? '측면' : '정면'} 사진을 먼저 올려주세요.
            </p>
          )}
        </div>
      </div>

      <div className="posture-upload-row">
        <PhotoSlot session={session} label={view === 'side' ? '측면' : '정면'} />
      </div>

      <div className="squat-card photo-panel photo-panel-full">
        <div className="photo-panel-head">
          <span>분석 결과</span>
          <button type="button" className="photo-detail-toggle-btn" onClick={() => setNoticeOpen(true)}>
            촬영 안내
          </button>
        </div>
        <AnalysisPanel session={session} view={view} />
      </div>

      <div className="squat-card photo-panel photo-panel-full reliability-notice">
        <div className="photo-panel-head">참고로 확인해보세요</div>
        <p className="reliability-notice-text">
          사진은 서버로 전송되지 않아요. 브라우저에서 관절 위치만 계산해 보냅니다.
          라운드숄더는 목뼈(C7) 위치를 어깨·골반 좌표로 근사해 계산하므로, 정확한 수치보다
          경향을 참고해주세요.
        </p>
      </div>

      {noticeOpen && <CaptureNoticeModal onClose={() => setNoticeOpen(false)} />}
    </PageShell>
  )
}

export default PosturePage

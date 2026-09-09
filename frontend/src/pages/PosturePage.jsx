/**
 * 정지 자세 분석 페이지 (/posture).
 *
 * 팀의 자세 측정 페이지(/exercises/photo)는 **운동 동작**(스쿼트)을 다루고,
 * 이 페이지는 **서 있는 정지 자세**를 다룬다. 측정하는 값도 다르다:
 *   정면 — 어깨·골반 좌우 기울기
 *   측면 — 전방머리자세, 라운드숄더
 *
 * 사진은 서버로 보내지 않는다. 브라우저에서 MediaPipe로 좌표만 뽑아
 * posture-ai(:8001)로 전송한다 — 신체 사진이 기기를 벗어나지 않는다.
 */

import { useRef, useState } from 'react'
import PageShell from '../components/PageShell.jsx'
import Modal from '../components/Modal.jsx'
import { usePostureSession } from '../hooks/usePostureSession.js'
import './PosturePage.css'

const VIEWS = [
  { key: 'side', label: '측면', hint: '옆으로 서서 촬영해 주세요' },
  { key: 'front', label: '정면', hint: '정면을 보고 서서 촬영해 주세요' },
]

const VERDICT_CLASS = {
  정상: 'posture-verdict-normal',
  경미: 'posture-verdict-mild',
  주의: 'posture-verdict-warn',
}

/**
 * 촬영 전 안내 모달.
 *
 * 팀 PhotoCoachingPage의 UploadNoticeModal과 같은 패턴을 쓴다 — 공용
 * Modal.jsx + closeOnBackdropClick(안내성 모달이라 바깥 클릭으로도 닫힘)
 * + 상태 초깃값 true(페이지에 들어올 때마다 자동으로 열림).
 *
 * 안내 항목은 posture-ai의 실제 검증 조건과 맞췄다. 예를 들어 "몸이 완전히
 * 옆을 향하게"는 quality.py의 MAX_SIDE_SHOULDER_X / MIN_Z_SEPARATION 검사가
 * 실제로 걸러내는 조건이고, "전신이 나오도록"은 REQUIRED_KEYPOINTS 미검출을
 * 막기 위한 것이다. 검증에서 안 보는 항목(배경, 카메라 높이 등)은 넣지
 * 않았다 — 지키지 않아도 결과가 달라지지 않는 안내는 읽는 부담만 준다.
 */
function CaptureNoticeModal({ onClose }) {
  return (
    <Modal onClose={onClose} className="posture-notice-modal" closeOnBackdropClick>
      <div className="modal-title">촬영 전 확인해 주세요</div>
      <ul className="posture-notice-list">
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

/**
 * 지표별 3구간 정의.
 *
 * 눈금(숫자)을 그리지 않는 이유:
 *   forward_head 구간(15/25도)은 임상 확립 기준이 없는 잠정값이고,
 *   round_shoulder는 C7을 어깨-골반 좌표로 근사해 계산한 값이라
 *   정밀도가 낮다. 눈금을 그리면 근거가 약한 숫자를 정확한 것처럼
 *   보이게 만든다 — 이 프로젝트가 문서 전반에서 "정량 수치보다 정성
 *   경향"을 원칙으로 삼아온 이유다. 그래서 구간은 색으로만 구분하고
 *   마커로 "어디쯤인지"만 보여준다.
 *
 * inverted: round_shoulder는 값이 **클수록** 정상이다(견봉-C7 선이
 *   수직에 가까울수록 어깨가 안 말린 상태). 나머지는 절댓값이 작을수록
 *   정상이라 방향이 반대다.
 */
const METRIC_BANDS = {
  shoulder: { normal: 5, mild: 15, max: 25, inverted: false },
  pelvis: { normal: 5, mild: 15, max: 25, inverted: false },
  forward_head: { normal: 15, mild: 25, max: 45, inverted: false },
  round_shoulder: { normal: 52, mild: 45, max: 90, inverted: true },
}

/**
 * 값이 막대의 몇 % 지점에 오는지 계산한다(0~100).
 * 막대는 왼쪽이 정상, 오른쪽이 주의다 — inverted 지표는 뒤집어 매핑한다.
 */
function markerPercent(value, band) {
  if (band.inverted) {
    // 90도(완전 수직=가장 정상)를 왼쪽 끝, 0도를 오른쪽 끝으로
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

function MetricCard({ title, metricKey, metric }) {
  if (!metric) return null

  const band = METRIC_BANDS[metricKey]
  const widths = band ? bandWidths(band) : null
  const percent = band ? markerPercent(metric.angle_deg, band) : null

  return (
    <div className="posture-metric">
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
      <div className="posture-metric-angle">측정값 {metric.angle_deg}도</div>
      {metric.note && <p className="posture-metric-note">{metric.note}</p>}
    </div>
  )
}

function PosturePage() {
  const [view, setView] = useState('side')
  // 페이지에 들어올 때마다 안내를 먼저 보여준다(팀 PhotoCoachingPage와 동일).
  const [noticeOpen, setNoticeOpen] = useState(true)
  const fileRef = useRef(null)
  const { previewUrl, status, result, error, analyze, reset, isBusy } =
    usePostureSession(view)

  const current = VIEWS.find((v) => v.key === view)

  const handleFile = (event) => {
    const file = event.target.files?.[0]
    if (file) analyze(file)
    event.target.value = '' // 같은 파일을 다시 골라도 onChange가 뜨도록
  }

  const handleViewChange = (key) => {
    if (key === view) return
    setView(key)
    reset()
  }

  const unreliable = result && !result.reliability.is_reliable

  return (
    <PageShell>
      <div className="posture-page">
        <div className="posture-header-row">
          <div>
            <p className="posture-eyebrow">자세 측정</p>
            <h1 className="posture-title">서 있는 자세 분석</h1>
          </div>
          <div className="posture-header-actions">
            <button
              type="button"
              className="posture-notice-btn"
              onClick={() => setNoticeOpen(true)}
            >
              촬영 안내
            </button>
            <div className="posture-view-tabs">
              {VIEWS.map((v) => (
                <button
                  key={v.key}
                  type="button"
                  className={
                    v.key === view ? 'posture-view-tab is-active' : 'posture-view-tab'
                  }
                  onClick={() => handleViewChange(v.key)}
                  disabled={isBusy}
                >
                  {v.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        <p className="posture-hint">{current.hint}</p>

        <div className="posture-body">
          <div className="posture-upload">
            {previewUrl ? (
              <img className="posture-preview" src={previewUrl} alt="업로드한 사진" />
            ) : (
              <div className="posture-placeholder">
                <p>사진을 올려주세요</p>
                <span>JPG · PNG · 10MB 이하</span>
              </div>
            )}

            <input
              ref={fileRef}
              type="file"
              accept="image/jpeg,image/png"
              onChange={handleFile}
              hidden
            />
            <div className="posture-actions">
              <button
                type="button"
                className="posture-btn-primary"
                onClick={() => fileRef.current?.click()}
                disabled={isBusy}
              >
                {previewUrl ? '다른 사진 올리기' : '사진 올리기'}
              </button>
              {previewUrl && (
                <button
                  type="button"
                  className="posture-btn-ghost"
                  onClick={reset}
                  disabled={isBusy}
                >
                  지우기
                </button>
              )}
            </div>

            <p className="posture-privacy">
              사진은 서버로 전송되지 않습니다. 브라우저에서 관절 위치만 계산해 보냅니다.
            </p>
          </div>

          <div className="posture-result">
            {status === 'detecting' && <p className="posture-status">자세를 인식하는 중…</p>}
            {status === 'analyzing' && <p className="posture-status">분석하는 중…</p>}
            {error && <p className="posture-error">{error}</p>}

            {result && (
              <>
                {unreliable && (
                  <div className="posture-warning">
                    <strong>이 결과는 신뢰하기 어렵습니다.</strong>
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
                      <MetricCard
                        title="전방머리자세"
                        metricKey="forward_head"
                        metric={result.forward_head}
                      />
                      <MetricCard
                        title="라운드숄더"
                        metricKey="round_shoulder"
                        metric={result.round_shoulder}
                      />
                    </>
                  ) : (
                    <>
                      <MetricCard
                        title="어깨 좌우 기울기"
                        metricKey="shoulder"
                        metric={result.shoulder}
                      />
                      <MetricCard
                        title="골반 좌우 기울기"
                        metricKey="pelvis"
                        metric={result.pelvis}
                      />
                    </>
                  )}
                </div>

                {result.comment?.text && (
                  <div className="posture-comment">
                    <p>{result.comment.text}</p>
                  </div>
                )}

                {result.keypoint_confidence?.length > 0 && (
                  <details className="posture-detail">
                    <summary>관절 인식 신뢰도</summary>
                    <ul>
                      {result.keypoint_confidence.map((kp) => (
                        <li key={kp.name}>
                          {kp.name} — {kp.band}
                        </li>
                      ))}
                    </ul>
                  </details>
                )}

                <p className="posture-disclaimer">{result.disclaimer}</p>
              </>
            )}
          </div>
        </div>
      </div>

      {noticeOpen && <CaptureNoticeModal onClose={() => setNoticeOpen(false)} />}
    </PageShell>
  )
}

export default PosturePage

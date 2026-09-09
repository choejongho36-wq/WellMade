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

function MetricCard({ title, metric }) {
  if (!metric) return null
  return (
    <div className="posture-metric">
      <div className="posture-metric-head">
        <span className="posture-metric-title">{title}</span>
        <span className={`posture-verdict ${VERDICT_CLASS[metric.verdict] || ''}`}>
          {metric.verdict}
        </span>
      </div>
      <div className="posture-metric-angle">{metric.angle_deg}도</div>
      {metric.note && <p className="posture-metric-note">{metric.note}</p>}
    </div>
  )
}

function PosturePage() {
  const [view, setView] = useState('side')
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
        <div className="page-eyebrow-row">
          <div>
            <p className="posture-eyebrow">자세 분석</p>
            <h1 className="posture-title">서 있는 자세 측정</h1>
          </div>
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
                      <MetricCard title="전방머리자세" metric={result.forward_head} />
                      <MetricCard title="라운드숄더" metric={result.round_shoulder} />
                    </>
                  ) : (
                    <>
                      <MetricCard title="어깨 좌우 기울기" metric={result.shoulder} />
                      <MetricCard title="골반 좌우 기울기" metric={result.pelvis} />
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
    </PageShell>
  )
}

export default PosturePage

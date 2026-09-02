/**
 * 사진 코칭(②-A) 페이지 — 서비스 흐름도의 "② 코칭 모드 선택"에서 "사진 코칭"을 고르면
 * 오는 화면.
 *
 * 2026-09-02 대규모 개편(사용자 피드백 반영):
 * 1. 업로드 안내 문구를 헤더(PHOTO COACHING 행) 바로 아래, 페이지 맨 위로 올림.
 * 2. 사진 미리보기를 정면(필수)/측면(선택) 2장으로 분리 — 정면 없이는 분석 불가,
 *    측면은 "선택" 배지로 표시.
 * 3. "분석 결과" 패널을 2단 그리드가 아니라 그 아래(전체 폭)로 내림.
 * 4. 각 미리보기는 드래그로 옮길 수 있는 분홍/파랑 좌표 점 오버레이(PhotoLandmarkEditor)로
 *    표시 — 좌표를 옮겨도 즉시 재계산하지 않고, "분석하기" 버튼을 눌렀을 때만 그 시점의
 *    좌표로 재계산한다(hooks/usePhotoCoachingSession.js 참고).
 * 5. "분석 결과"의 각도 숫자 막대(예전 ANALYSIS_METRICS)는 없애고, 규칙 기반 판정
 *    결과를 LLM(Nova, app/coaching/photo_summary_llm.py)이 정리한 문장으로 보여준다 —
 *    판정 자체는 여전히 규칙 기반이고 문장만 LLM이 담당.
 *
 * AI-06(judge_realtime_coaching)은 사진 한 장(측면)의 값을 타임스탬프만 다르게 3프레임
 * 복제해 보내면 "정지" 상태로 인식해 실제 임계값 비교를 그대로 적용해준다는 점은 이전과
 * 동일 — 측면 사진이 없으면 AI-06 자체를 호출하지 않고 정면만으로 계산 가능한 무릎 모임을
 * 프론트가 직접 판정한다.
 */

import { useState } from 'react'
import { Link } from 'react-router-dom'
import PageShell from '../components/PageShell.jsx'
import ExerciseGuideModal from '../components/ExerciseGuideModal.jsx'
import ExerciseSelectDropdown from '../components/ExerciseSelectDropdown.jsx'
import PhotoLandmarkEditor from '../components/PhotoLandmarkEditor.jsx'
import { usePhotoCoachingSession } from '../hooks/usePhotoCoachingSession.js'
import { PHOTO_DOT_LEFT_COLOR, PHOTO_DOT_RIGHT_COLOR } from '../lib/squatPose.js'
import './squatShared.css'
import './PhotoCoachingPage.css'

function PhotoSlotPanel({ slot, label, required, alt }) {
  return (
    <div className="squat-card photo-panel photo-slot-panel">
      <div className="photo-panel-head">
        사진 미리보기 · {label}
        <span className={required ? 'photo-req-badge' : 'photo-optional-badge'}>{required ? '필수' : '선택'}</span>
      </div>

      <div className="preview-frame">
        {slot.phase === 'idle' && (
          <button type="button" className="preview-placeholder" onClick={slot.openFilePicker}>
            <span className="preview-placeholder-icon">📷</span>
            {label} 사진을 업로드해주세요
          </button>
        )}
        {slot.phase === 'analyzing' && <div className="preview-placeholder preview-loading">자세 인식 중...</div>}
        {slot.phase === 'error' && (
          <button type="button" className="preview-placeholder" onClick={slot.openFilePicker}>
            <span className="preview-placeholder-icon">⚠️</span>
            {slot.poseError || '다시 시도해주세요'}
          </button>
        )}
        {slot.phase === 'ready' && slot.photoUrl && slot.points && (
          <>
            <PhotoLandmarkEditor
              photoUrl={slot.photoUrl}
              alt={alt}
              points={slot.points}
              onPointsChange={slot.setPoints}
              leftColor={PHOTO_DOT_LEFT_COLOR}
              rightColor={PHOTO_DOT_RIGHT_COLOR}
            />
            {slot.avgVisibility != null && (
              <div className="preview-legend">
                <span>
                  <i className="legend-dot" style={{ background: PHOTO_DOT_LEFT_COLOR }} />왼쪽 관절
                </span>
                <span>
                  <i className="legend-dot" style={{ background: PHOTO_DOT_RIGHT_COLOR }} />오른쪽 관절
                </span>
                <span>신뢰도 {Math.round(slot.avgVisibility * 100)}% · 점을 드래그해 위치를 고칠 수 있어요</span>
              </div>
            )}
          </>
        )}
        {slot.fileName && <p className="preview-filename">{slot.fileName}</p>}
      </div>

      {slot.fileError && <p className="squat-error">{slot.fileError}</p>}

      <input
        ref={slot.fileInputRef}
        type="file"
        accept="image/jpeg,image/png"
        className="photo-file-input"
        onChange={slot.onFileInputChange}
      />
      <button type="button" className="squat-btn squat-btn-outline" onClick={slot.openFilePicker}>
        {slot.phase === 'ready' ? '다른 사진 업로드' : '사진 업로드'}
      </button>
      <p className="photo-upload-caption">JPG · PNG · 최대 10MB</p>
    </div>
  )
}

function AnalysisPanel({ session }) {
  const { front, analyzing, judgeResult, judgeError, summary, summaryError } = session

  if (front.phase !== 'ready') {
    return <div className="analysis-empty">정면 사진을 올리고 "분석하기"를 누르면 결과가 이 자리에 표시돼요.</div>
  }
  if (analyzing) {
    return <div className="analysis-empty">AI가 자세를 분석하고 있어요...</div>
  }
  if (judgeError) {
    return <p className="squat-error">{judgeError}</p>
  }
  if (!judgeResult) {
    return <div className="analysis-empty">아래 "분석하기" 버튼을 누르면 결과가 표시돼요.</div>
  }

  return (
    <div>
      <div className="analysis-summary">
        <span className={judgeResult.is_normal ? 'photo-ok' : 'photo-warn'}>
          {judgeResult.is_normal ? '전체적으로 정상 범위예요' : '점검이 필요한 항목이 있어요'}
        </span>
        <span className="analysis-confidence">신뢰도 {Math.round(judgeResult.confidence * 100)}%</span>
      </div>

      {summaryError && <p className="squat-error">{summaryError}</p>}
      {summary && <p className="analysis-summary-text">{summary.summary_message}</p>}
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

      <div className="photo-warning-box photo-warning-box-top">
        <b>업로드 전 확인해 주세요.</b>
        <ul>
          <li>전신이 옆모습(측면)으로 잘 보이는 사진을 올려주세요.</li>
          <li>사진이 흐리거나 신체 일부가 가려지면 분석이 부정확하거나 실패할 수 있어요.</li>
          <li>이 분석 결과는 참고용이에요. 통증이 있다면 무리하지 말고 전문가와 상담해주세요.</li>
        </ul>
      </div>

      <div className="section-head">
        <div className="section-title">사진 코칭</div>
      </div>

      <div className="photo-upload-row">
        <PhotoSlotPanel slot={session.front} label="정면" required alt="업로드한 정면 스쿼트 자세" />
        <PhotoSlotPanel slot={session.side} label="측면" required={false} alt="업로드한 측면 스쿼트 자세" />
      </div>

      <div className="photo-analyze-row">
        <button
          type="button"
          className="squat-btn squat-btn-primary photo-analyze-btn"
          onClick={session.runAnalysis}
          disabled={!session.canAnalyze}
        >
          {session.analyzing ? '분석 중...' : '분석하기'}
        </button>
        {session.front.phase !== 'ready' && <p className="photo-analyze-hint">정면 사진을 먼저 올려주세요. 측면 사진은 선택이에요.</p>}
      </div>

      <div className="squat-card photo-panel photo-panel-full">
        <div className="photo-panel-head">분석 결과</div>
        <AnalysisPanel session={session} />
      </div>

      <p className="photo-back-link">
        <Link to="/squat">← 코칭 모드 다시 고르기</Link>
      </p>

      {guideOpen && <ExerciseGuideModal onClose={() => setGuideOpen(false)} />}
    </PageShell>
  )
}

export default PhotoCoachingPage

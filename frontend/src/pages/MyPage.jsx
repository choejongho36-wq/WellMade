import { useEffect, useState } from 'react'
import './MyPage.css'
import { useAuth } from '../lib/auth.js'
import PageShell from '../components/PageShell.jsx'

const GOAL_LABEL = {
  LOSE: '체중 감량',
  GAIN: '근육 증가',
  MAINTAIN: '체중 유지',
}

const PROVIDER_LABEL = {
  GOOGLE: '구글',
  KAKAO: '카카오',
  NAVER: '네이버',
}

const INBODY_FIELDS = [
  { key: 'weightKg', label: '체중', unit: 'kg', step: '0.1' },
  { key: 'skeletalMuscleMassKg', label: '골격근량', unit: 'kg', step: '0.1' },
  { key: 'bodyFatPercentage', label: '체지방률', unit: '%', step: '0.1' },
  { key: 'basalMetabolicRateKcal', label: '기초대사량', unit: 'kcal', step: '1' },
  { key: 'bmi', label: 'BMI', unit: '', step: '0.1' },
]

function InbodyUploadModal({ onClose, onExtract, onConfirm }) {
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [extracted, setExtracted] = useState(null)

  useEffect(() => {
    const onKeyDown = (e) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  useEffect(() => {
    return () => {
      if (preview) URL.revokeObjectURL(preview)
    }
  }, [preview])

  const handleFileChange = (e) => {
    const picked = e.target.files[0] ?? null
    setFile(picked)
    setPreview((prev) => {
      if (prev) URL.revokeObjectURL(prev)
      return picked ? URL.createObjectURL(picked) : null
    })
  }

  const handleExtract = () => {
    if (!file) return
    setLoading(true)
    setError('')
    onExtract(file)
      .then(setExtracted)
      .catch(() => setError('인식에 실패했어요. 다른 사진으로 다시 시도해주세요.'))
      .finally(() => setLoading(false))
  }

  const handleConfirm = () => {
    setLoading(true)
    setError('')
    onConfirm(extracted)
      .then(() => onClose())
      .catch(() => setError('등록에 실패했어요. 다시 시도해주세요.'))
      .finally(() => setLoading(false))
  }

  if (extracted) {
    return (
      <div className="modal-backdrop" onClick={onClose}>
        <div className="modal" onClick={(e) => e.stopPropagation()}>
          <button className="modal-close" onClick={onClose} aria-label="닫기">×</button>
          <div className="modal-title">인식 결과 확인</div>
          <div className="modal-sub">사진에서 읽은 값이 맞는지 확인해주세요</div>

          <div className="modal-review-list">
            {INBODY_FIELDS.map(({ key, label, unit, step }) => (
              <div className="modal-review-item" key={key}>
                <span>{label}</span>
                <span className="modal-review-input-wrap">
                  <input
                    type="number"
                    step={step}
                    className="modal-review-input"
                    placeholder="인식 안 됨"
                    value={extracted[key] ?? ''}
                    onChange={(e) => {
                      const v = e.target.value
                      setExtracted((prev) => ({ ...prev, [key]: v === '' ? null : Number(v) }))
                    }}
                  />
                  {unit && <span className="modal-review-unit">{unit}</span>}
                </span>
              </div>
            ))}
          </div>

          {error && <p style={{ color: '#da291c', fontSize: 12.5 }}>{error}</p>}
          <div className="modal-btn-row">
            <button className="modal-btn-secondary" onClick={() => setExtracted(null)} disabled={loading}>
              다시 선택
            </button>
            <button className="modal-btn" onClick={handleConfirm} disabled={loading}>
              {loading ? '등록 중...' : '확인, 등록하기'}
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose} aria-label="닫기">×</button>
        <div className="modal-title">인바디 등록</div>
        <div className="modal-sub">인바디 측정지 사진을 올려주세요</div>

        <label className="modal-upload" htmlFor="inbody-file">
          {preview ? (
            <img src={preview} alt="" className="modal-upload-preview" />
          ) : (
            <>
              <span className="modal-upload-icon">＋</span>
              <span className="modal-upload-text">사진 선택하기</span>
            </>
          )}
        </label>
        <input
          id="inbody-file"
          type="file"
          accept="image/*"
          className="modal-file-input"
          onChange={handleFileChange}
        />
        {file && <div className="modal-file-name">{file.name}</div>}

        {error && <p style={{ color: '#da291c', fontSize: 12.5 }}>{error}</p>}
        <button className="modal-btn" onClick={handleExtract} disabled={!file || loading}>
          {loading ? '분석 중...' : '다음'}
        </button>
      </div>
    </div>
  )
}

function MyPage() {
  const { user, profile, inbody, updateGoal, updateName, extractInbody, confirmInbody } = useAuth()
  const [modalOpen, setModalOpen] = useState(false)
  const [editingName, setEditingName] = useState(false)
  const [nameDraft, setNameDraft] = useState('')
  const [nameError, setNameError] = useState('')

  const startEditName = () => {
    setNameDraft(profile?.name ?? '')
    setNameError('')
    setEditingName(true)
  }

  const submitName = () => {
    const trimmed = nameDraft.trim()
    if (!trimmed || trimmed === profile?.name) {
      setEditingName(false)
      return
    }
    updateName(trimmed)
      .then(() => setEditingName(false))
      .catch((e) => setNameError(e.message || '변경에 실패했어요'))
  }

  return (
    <PageShell>
      <div className="mp-eyebrow-row">
        <div className="mp-index-tag">MY PAGE</div>
      </div>
      
      {user ? (
        <>
          <div className="mp-profile-row">
            <div className="mp-avatar-lg"></div>
            <div>
              <div className="mp-profile-name-row">
                {editingName ? (
                  <input
                    className="mp-name-input"
                    value={nameDraft}
                    autoFocus
                    maxLength={50}
                    onChange={(e) => setNameDraft(e.target.value)}
                    onBlur={submitName}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') submitName()
                      if (e.key === 'Escape') setEditingName(false)
                    }}
                  />
                ) : (
                  <>
                    <span className="mp-profile-name">{profile?.name ?? '이름 미설정'}</span>
                    <button className="mp-edit-btn" onClick={startEditName} aria-label="닉네임 변경">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M12 20h9" />
                        <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4Z" />
                      </svg>
                    </button>
                  </>
                )}
                <span className="mp-goal-bib">
                  <select
                    className="mp-goal-select"
                    value={profile?.goal ?? ''}
                    onChange={(e) => updateGoal(e.target.value)}
                  >
                    <option value="" disabled>
                      목표 설정
                    </option>
                    {Object.entries(GOAL_LABEL).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </span>
              </div>
              {nameError && <div className="mp-name-error">{nameError}</div>}
              <div className="mp-profile-sub">
                {user.email} · {PROVIDER_LABEL[user.provider] ?? user.provider} 로그인
              </div>
            </div>
          </div>

          <div className="mp-section-head">
            <div className="mp-section-title">인바디</div>
            {inbody && (
              <button className="mp-link-btn" onClick={() => setModalOpen(true)}>
                다시 입력
              </button>
            )}
          </div>

          {inbody ? (
            <div className="mp-stat-strip">
              {INBODY_FIELDS.map(({ key, label, unit }) => (
                <div className="mp-tag" key={key}>
                  <div className="mp-tag-inner">
                    <div className="mp-tag-label">{label}</div>
                    <div className="mp-tag-value">{inbody[key] != null ? inbody[key] : '-'}</div>
                    {unit && <div className="mp-tag-unit">{unit}</div>}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="mp-inbody-empty">
              <div className="mp-inbody-empty-inner">
                <div className="mp-goal-title">인바디 정보가 없어요</div>
                <p className="mp-profile-sub">
                  인바디 측정지 사진을 등록하면 체중·골격근량·체지방률을 자동으로 불러와요.
                </p>
                <button className="mp-inbody-btn" onClick={() => setModalOpen(true)}>
                  인바디 등록하기
                </button>
              </div>
            </div>
          )}
        </>
      ) : (
        <p className="pcard-desc">로그인 후 프로필을 확인할 수 있습니다.</p>
      )}

      {modalOpen && (
        <InbodyUploadModal
          onClose={() => setModalOpen(false)}
          onExtract={extractInbody}
          onConfirm={confirmInbody}
        />
      )}
    </PageShell>
  )
}

export default MyPage

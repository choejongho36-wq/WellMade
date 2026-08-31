import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import './MyPage.css'
import { useAuth } from '../lib/auth.js'
import PageShell from '../components/PageShell.jsx'
import NutrientDetailModal from '../components/NutrientDetailModal.jsx'
import profileImg from '../assets/profile.webp'
import { getBmiInsight } from '../lib/aiApi.js'

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

const DIET_HEADLINE_FIELD = { key: 'totalCalories', unit: 'kcal' }

const TREND_METRICS = [
  { key: 'weightKg', label: '체중', unit: 'kg' },
  { key: 'skeletalMuscleMassKg', label: '골격근량', unit: 'kg' },
  { key: 'bodyFatPercentage', label: '체지방률', unit: '%' },
  { key: 'bmi', label: 'BMI', unit: '' },
]
const TREND_PERIODS = [
  { label: '1개월', months: 1 },
  { label: '3개월', months: 3 },
  { label: '6개월', months: 6 },
  { label: '전체', months: null },
]

function Sparkline({ points }) {
  const w = 240
  const h = 52
  const pad = 5
  const xs = points.map((p) => p.t)
  const ys = points.map((p) => p.v)
  const minX = Math.min(...xs)
  const maxX = Math.max(...xs)
  const minY = Math.min(...ys)
  const maxY = Math.max(...ys)
  const sx = (t) => pad + ((t - minX) / (maxX - minX || 1)) * (w - pad * 2)
  const sy = (v) => pad + (1 - (v - minY) / (maxY - minY || 1)) * (h - pad * 2)
  const d = points.map((p, i) => `${i ? 'L' : 'M'}${sx(p.t).toFixed(1)} ${sy(p.v).toFixed(1)}`).join(' ')
  const last = points[points.length - 1]

  return (
    <svg className="mp-spark" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
      <path className="mp-spark-line" d={d} vectorEffect="non-scaling-stroke" />
      <circle className="mp-spark-dot" cx={sx(last.t)} cy={sy(last.v)} r={3} vectorEffect="non-scaling-stroke" />
    </svg>
  )
}

function MiniTrend({ metric, points }) {
  const latest = points.length ? points[points.length - 1].v : null
  const delta = points.length >= 2 ? latest - points[0].v : null

  return (
    <div className="mp-mini">
      <div className="mp-mini-head">
        <span className="mp-mini-label">{metric.label}</span>
        {delta != null && (
          <span className={`mp-mini-delta${delta > 0 ? ' up' : delta < 0 ? ' down' : ''}`}>
            {delta > 0 ? '+' : ''}{delta.toFixed(1)}{metric.unit}
          </span>
        )}
      </div>
      <div className="mp-mini-value">
        {latest != null ? latest : '-'}
        {metric.unit && <span className="mp-mini-unit">{metric.unit}</span>}
      </div>
      {points.length >= 2 ? (
        <Sparkline points={points} />
      ) : (
        <div className="mp-mini-empty">기록 부족</div>
      )}
    </div>
  )
}

function InbodyTrendChart({ history }) {
  const [months, setMonths] = useState(3)

  const cutoff = months ? Date.now() - months * 30 * 24 * 3600 * 1000 : 0
  const inRange = history.filter((r) => new Date(r.measuredAt).getTime() >= cutoff)

  return (
    <div className="mp-trend">
      <div className="mp-trend-tabs">
        {TREND_PERIODS.map((p) => (
          <button
            key={p.label}
            className={`mp-trend-tab${p.months === months ? ' active' : ''}`}
            onClick={() => setMonths(p.months)}
          >
            {p.label}
          </button>
        ))}
      </div>
      <div className="mp-trend-grid">
        {TREND_METRICS.map((m) => {
          const points = inRange
            .filter((r) => r[m.key] != null)
            .map((r) => ({ t: new Date(r.measuredAt).getTime(), v: r[m.key] }))
          return <MiniTrend key={m.key} metric={m} points={points} />
        })}
      </div>
    </div>
  )
}

function todayStr() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

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

const GENDER_LABEL = { MALE: '남성', FEMALE: '여성' }

function BodyInfoModal({ profile, onClose, onSave }) {
  const [gender, setGender] = useState(profile?.gender ?? null)
  const [heightCm, setHeightCm] = useState(profile?.heightCm ?? '')
  const [birthYear, setBirthYear] = useState(profile?.birthYear ?? '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const height = Number(heightCm)
  const year = Number(birthYear)
  const valid =
    gender &&
    height >= 100 && height <= 250 &&
    year >= 1900 && year <= new Date().getFullYear()

  const handleSave = () => {
    setSaving(true)
    setError('')
    onSave({ gender, heightCm: height, birthYear: year })
      .then(onClose)
      .catch((e) => setError(e.message || '저장에 실패했어요'))
      .finally(() => setSaving(false))
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose} aria-label="닫기">×</button>
        <div className="modal-title">신체 정보</div>
        <div className="modal-sub">
          기초대사량과 목표 칼로리는 성별·키·나이에 따라 달라져요. 입력하면 더 정확한 수치로 계산돼요.
        </div>

        <div className="mp-body-field">
          <span className="mp-body-label">성별</span>
          <div className="mp-body-genders">
            {Object.entries(GENDER_LABEL).map(([value, label]) => (
              <button
                key={value}
                className={`mp-trend-tab${gender === value ? ' active' : ''}`}
                onClick={() => setGender(value)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className="mp-body-field">
          <span className="mp-body-label">키</span>
          <span className="modal-review-input-wrap">
            <input
              type="number"
              step="0.1"
              className="modal-review-input"
              value={heightCm}
              onChange={(e) => setHeightCm(e.target.value)}
            />
            <span className="modal-review-unit">cm</span>
          </span>
        </div>

        <div className="mp-body-field">
          <span className="mp-body-label">출생연도</span>
          <span className="modal-review-input-wrap">
            <input
              type="number"
              step="1"
              className="modal-review-input"
              value={birthYear}
              onChange={(e) => setBirthYear(e.target.value)}
            />
            <span className="modal-review-unit">년</span>
          </span>
        </div>

        {error && <p className="mp-name-error">{error}</p>}
        <button className="modal-btn" onClick={handleSave} disabled={!valid || saving}>
          {saving ? '저장 중...' : '저장하기'}
        </button>
      </div>
    </div>
  )
}

function GoalPickerModal({ current, onClose, onSelect }) {
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose} aria-label="닫기">×</button>
        <div className="modal-title">목표 설정</div>
        <div className="goal-option-list">
          {Object.entries(GOAL_LABEL).map(([value, label]) => (
            <button
              key={value}
              className={`goal-option${value === current ? ' selected' : ''}`}
              onClick={() => onSelect(value)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

function MyPage() {
  const [bmiInsight, setBmiInsight] = useState(null)
  const { user, profile, inbody, updateGoal, updateName, updateBody, extractInbody, confirmInbody, getInbodyHistory, getTodayTotal, getNutrientTarget, deleteAccount } = useAuth()
  const navigate = useNavigate()
  const [inbodyHistory, setInbodyHistory] = useState([])
  const [bodyModalOpen, setBodyModalOpen] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editingName, setEditingName] = useState(false)
  const [nameDraft, setNameDraft] = useState('')
  const [nameError, setNameError] = useState('')
  const [todaySummary, setTodaySummary] = useState(null)
  const [nutrientTarget, setNutrientTarget] = useState(null)
  const [nutrientModalOpen, setNutrientModalOpen] = useState(false)
  const [goalModalOpen, setGoalModalOpen] = useState(false)
  const [withdrawModalOpen, setWithdrawModalOpen] = useState(false)
  const [withdrawing, setWithdrawing] = useState(false)
  const [withdrawError, setWithdrawError] = useState('')
  const [firstInbodyGuide, setFirstInbodyGuide] = useState(false)

  useEffect(() => {
    if (user) getTodayTotal(todayStr()).then(setTodaySummary).catch(() => {})
  }, [user])

  useEffect(() => {
    if (user) getNutrientTarget().then(setNutrientTarget).catch(() => {})
  }, [user])

  // inbody(최신 레코드)가 바뀌면 = 새로 등록됐으면 추이도 다시 불러옴
  useEffect(() => {
    if (user) getInbodyHistory().then(setInbodyHistory).catch(() => {})
  }, [user, inbody])

  // BMI 또래 비교(AI 서버). 성별·출생년도가 없으면 비교 자체가 불가능해서 건너뛴다.
  // 실패하면 null이 와서 아래 섹션이 그냥 안 보인다 - 인바디 화면 자체는 영향받지 않는다
  useEffect(() => {
    getBmiInsight({
      bmi: inbody?.bmi,
      gender: profile?.gender,
      birthYear: profile?.birthYear,
    }).then(setBmiInsight)
  }, [inbody?.bmi, profile?.gender, profile?.birthYear])

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

  // 목표가 바뀌면 목표 칼로리도 그 목표 기준으로 다시 계산되므로, 프로필 갱신에 이어서
  // 새로고침 없이 바로 반영되도록 여기서 같이 다시 불러옴
  const selectGoal = (goal) => {
    updateGoal(goal)
      .then(() => getNutrientTarget())
      .then(setNutrientTarget)
      .catch(() => {})
      .finally(() => setGoalModalOpen(false))
  }

  // 성별/키/나이가 바뀌면 기초대사량 추정이 달라져서 목표 칼로리도 다시 계산됨 - 목표 변경과 같은 이유로 다시 불러옴
  const saveBody = (values) =>
    updateBody(values).then(() => getNutrientTarget().then(setNutrientTarget).catch(() => {}))

  const hasBodyInfo = Boolean(profile?.gender && profile?.heightCm && profile?.birthYear)

  // 첫 등록이면 추이 그래프가 왜 아직 안 보이는지 알려준다 (두 개부터 그려짐).
  // inbody는 등록 전 값이라 여기서 판단할 수 있음 - confirmInbody가 성공한 뒤 갱신된다
  const handleConfirmInbody = (values) => {
    const isFirst = !inbody
    return confirmInbody(values).then((data) => {
      if (isFirst) setFirstInbodyGuide(true)
      return data
    })
  }

  const handleWithdraw = () => {
    setWithdrawing(true)
    setWithdrawError('')
    deleteAccount()
      .then(() => navigate('/'))
      .catch((e) => setWithdrawError(e.message || '탈퇴에 실패했어요'))
      .finally(() => setWithdrawing(false))
  }

  return (
    <PageShell>
      <div className="page-eyebrow-row">
        <div className="page-index-tag">MY PAGE</div>
      </div>
      
      {user ? (
        <>
          <div className="mp-profile-row">
            <div className="mp-avatar-lg">
              <img src={profileImg} alt="" className="mp-avatar-img" />
            </div>
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
                  <button className="mp-goal-select" onClick={() => setGoalModalOpen(true)}>
                    {GOAL_LABEL[profile?.goal] ?? '목표 설정'}
                  </button>
                </span>
              </div>
              {nameError && <div className="mp-name-error">{nameError}</div>}
              <div className="mp-profile-sub">
                {user.email}
                {hasBodyInfo && (
                  <>
                    {' · '}
                    {GENDER_LABEL[profile.gender]} · {profile.heightCm}cm · 만{' '}
                    {new Date().getFullYear() - profile.birthYear}세
                    <button className="link-btn mp-body-edit" onClick={() => setBodyModalOpen(true)}>
                      수정
                    </button>
                  </>
                )}
              </div>
            </div>
            <button className="mp-withdraw-btn" onClick={() => setWithdrawModalOpen(true)}>
              회원탈퇴
            </button>
          </div>

          {profile && !hasBodyInfo && (
            <div className="mp-body-prompt">
              <div>
                <div className="mp-goal-title">신체 정보를 입력해주세요</div>
                <p className="mp-profile-sub">
                  기초대사량과 목표 칼로리는 성별·키·나이에 따라 크게 달라져요. 지금은 체중만으로
                  대략 추정한 값이라 실제와 차이가 있을 수 있어요.
                </p>
              </div>
              <button className="mp-inbody-btn" onClick={() => setBodyModalOpen(true)}>
                입력하기
              </button>
            </div>
          )}

          <div className="section-head">
            <div className="section-title">인바디</div>
            {inbody && (
              <button className="link-btn" onClick={() => setModalOpen(true)}>
                다시 입력
              </button>
            )}
          </div>

          {inbody ? (
            <>
              <div className="tag-strip">
                {INBODY_FIELDS.map(({ key, label, unit }) => (
                  <div className="tag" key={key}>
                    <div className="tag-label"><span>{label}</span></div>
                    <div className="tag-inner">
                      <div className="tag-value">{inbody[key] != null ? inbody[key] : '-'}</div>
                      {unit && <div className="tag-unit">{unit}</div>}
                    </div>
                  </div>
                ))}
              </div>

              {/* BMI 또래 비교 - 분류만 보면 "나만 그런가?"를, 백분위만 보면
                  "또래도 다 그러니 괜찮다"를 오해하게 되어 둘을 같이 보여준다 */}
              {bmiInsight && (
                <p className="mp-bmi-insight">
                  {bmiInsight.message}
                  <span className="mp-bmi-source">
                    {bmiInsight.source} 기준 · 대한비만학회 분류
                  </span>
                </p>
              )}
            </>
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

          {inbodyHistory.length >= 2 && (
            <>
              <div className="section-head">
                <div className="section-title">인바디 추이</div>
              </div>
              <InbodyTrendChart history={inbodyHistory} />
            </>
          )}

          <div className="section-head">
            <div className="section-title">오늘 식단</div>
            <Link className="link-btn" to="/mealplan">식단 기록으로 이동</Link>
          </div>
          {todaySummary && (
            <div className="summary-row">
              <span className="summary-row-label">총 섭취</span>
              <div className="tag-strip">
                <button className="tag tag-clickable" onClick={() => setNutrientModalOpen(true)}>
                  <div className="tag-inner">
                    <div className="tag-value">{Math.round(todaySummary[DIET_HEADLINE_FIELD.key])}</div>
                    <div className="tag-unit">{DIET_HEADLINE_FIELD.unit}</div>
                  </div>
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
          onConfirm={handleConfirmInbody}
        />
      )}
      {firstInbodyGuide && (
        <div className="modal-backdrop" onClick={() => setFirstInbodyGuide(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <button className="modal-close" onClick={() => setFirstInbodyGuide(false)} aria-label="닫기">×</button>
            <div className="modal-title">첫 인바디가 등록됐어요</div>
            <div className="modal-sub">
              이제 체중·골격근량·체지방률을 기준으로 목표 칼로리가 계산돼요.
            </div>
            <p className="pcard-desc">
              변화 추이 그래프는 기록이 <strong>두 개 이상</strong>일 때부터 그려져요.
              다음에 인바디를 측정하면 "다시 입력"으로 등록해주세요 — 그때부터 체중과 근육량이
              어떻게 변했는지 한눈에 볼 수 있어요.
            </p>
            <button className="modal-btn" onClick={() => setFirstInbodyGuide(false)}>확인했어요</button>
          </div>
        </div>
      )}
      {nutrientModalOpen && (
        <NutrientDetailModal
          summary={todaySummary}
          target={nutrientTarget}
          onTargetChange={setNutrientTarget}
          onClose={() => setNutrientModalOpen(false)}
        />
      )}
      {bodyModalOpen && (
        <BodyInfoModal
          profile={profile}
          onClose={() => setBodyModalOpen(false)}
          onSave={saveBody}
        />
      )}
      {goalModalOpen && (
        <GoalPickerModal
          current={profile?.goal}
          onClose={() => setGoalModalOpen(false)}
          onSelect={selectGoal}
        />
      )}
      {withdrawModalOpen && (
        <div className="modal-backdrop" onClick={() => !withdrawing && setWithdrawModalOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <button
              className="modal-close"
              onClick={() => setWithdrawModalOpen(false)}
              disabled={withdrawing}
              aria-label="닫기"
            >
              ×
            </button>
            <div className="modal-title">정말 탈퇴하시겠어요?</div>
            <div className="modal-sub">
              인바디, 식단 기록, 챗봇 대화 이력이 전부 삭제되고 복구할 수 없어요.
            </div>
            {withdrawError && <p className="mp-name-error">{withdrawError}</p>}
            <div className="modal-btn-row">
              <button
                className="modal-btn-secondary"
                onClick={() => setWithdrawModalOpen(false)}
                disabled={withdrawing}
              >
                취소
              </button>
              <button className="modal-btn" onClick={handleWithdraw} disabled={withdrawing}>
                {withdrawing ? '탈퇴 중...' : '탈퇴하기'}
              </button>
            </div>
          </div>
        </div>
      )}
    </PageShell>
  )
}

export default MyPage

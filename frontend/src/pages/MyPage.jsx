import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import './MyPage.css'
import { useAuth } from '../lib/auth.js'
import { todayStr } from '../lib/dates.js'
import PageShell from '../components/PageShell.jsx'
import NutrientDetailModal from '../components/NutrientDetailModal.jsx'
import profileImg from '../assets/profile.webp'
import { getBmiInsight } from '../lib/aiApi.js'
import { MEAL_TYPE_LABEL } from '../lib/mealTypes.js'

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
// 마이페이지 카드에는 아침/점심/저녁만 세 칸으로 - 간식까지 넣으면 칸이 늘어져서
// 전체 타임라인(식단 기록 페이지)에서 보게 두고 여기선 뺐다
const MEAL_SLOTS = ['BREAKFAST', 'LUNCH', 'DINNER']

// 히어로에 크게 띄우는 대표 지표 - 나머지는 "자세히 보기"를 눌러야 펼쳐진다
const HERO_METRIC = { key: 'weightKg', label: '체중', unit: 'kg' }
const DETAIL_METRICS = [
  { key: 'skeletalMuscleMassKg', label: '골격근량', unit: 'kg' },
  { key: 'bodyFatPercentage', label: '체지방률', unit: '%' },
  { key: 'basalMetabolicRateKcal', label: '기초대사량', unit: 'kcal' },
  { key: 'bmi', label: 'BMI', unit: '' },
]
const TREND_PERIODS = [
  { label: '1개월', months: 1 },
  { label: '3개월', months: 3 },
  { label: '6개월', months: 6 },
  { label: '전체', months: null },
]

function Sparkline({ points, area }) {
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
   
    <div className="mp-spark-wrap">
      <svg className={`mp-spark${area ? ' mp-spark-lg' : ''}`} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
        {area && (
          <>
            <defs>
              <linearGradient id="mp-spark-grad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#da291c" stopOpacity="0.22" />
                <stop offset="100%" stopColor="#da291c" stopOpacity="0" />
              </linearGradient>
            </defs>
            <line className="mp-spark-grid" x1="0" y1={h * 0.28} x2={w} y2={h * 0.28} />
            <line className="mp-spark-grid" x1="0" y1={h * 0.64} x2={w} y2={h * 0.64} />
            <path className="mp-spark-fill" d={`${d} L${sx(maxX).toFixed(1)} ${h} L${sx(minX).toFixed(1)} ${h} Z`} />
          </>
        )}
        <path className="mp-spark-line" d={d} vectorEffect="non-scaling-stroke" />
      </svg>
      <span
        className="mp-spark-dot"
        style={{ left: `${(sx(last.t) / w) * 100}%`, top: `${(sy(last.v) / h) * 100}%` }}
      />
    </div>
  )
}

function MiniTrend({ metric, points, fallback }) {
  const latest = points.length ? points[points.length - 1].v : fallback ?? null
  const delta = points.length >= 2 ? points[points.length - 1].v - points[0].v : null

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
        <>
          <Sparkline points={points} />
          <div className="mp-mini-axis">
            <span>{shortDate(points[0].t)}</span>
            <span>{shortDate(points[points.length - 1].t)}</span>
          </div>
        </>
      ) : (
        <div className="mp-mini-empty">다음 측정부터 추이가 그려져요</div>
      )}
    </div>
  )
}

// LocalDateTime이 타임존 없이 "2026-08-30T09:12:00"으로 오므로 Date 파싱 없이 문자열을 자른다
function measuredDate(iso) {
  return iso ? iso.slice(0, 10).replace(/-/g, '.') : ''
}

// 처음·중간·마지막 3개만 - 점이 많아도 축이 빽빽해지지 않는다
function axisTicks(points) {
  if (points.length < 3) return points.map((p) => p.t)
  return [points[0].t, points[Math.floor(points.length / 2)].t, points[points.length - 1].t]
}

function shortDate(t) {
  const d = new Date(t)
  return `${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getDate()).padStart(2, '0')}`
}

// 목표 대비 원(클릭하면 영양소 상세 모달) + 아침/점심/저녁 세 칸 - 탄단지 수치는
// 이미 상세 모달에 다 있어서 여기서는 "오늘 뭘 먹었나"만 한눈에 보여준다
function DietTodayCard({ summary, meals, target, onOpenDetail }) {
  const kcal = summary ? Math.round(summary[DIET_HEADLINE_FIELD.key]) : null
  const goal = target?.kcal ? Math.round(target.kcal) : null
  const percent = kcal != null && goal ? Math.min(999, Math.round((kcal / goal) * 100)) : null
  const left = kcal != null && goal ? goal - kcal : null
  // r=32 원 둘레 201.06 - 채운 만큼만 남기고 나머지를 offset으로 밀어낸다
  const dash = 201.06
  const offset = percent != null ? dash * (1 - Math.min(percent, 100) / 100) : dash

  return (
    <div className="mp-diet-card">
      <div className="mp-diet-head">
        <span className="mp-diet-label">오늘 식단</span>
        <Link className="link-btn" to="/mealplan">기록하러 가기</Link>
      </div>

      <button className="mp-diet-ring-row" onClick={onOpenDetail} disabled={kcal == null}>
        <div className="mp-diet-ring">
          <svg viewBox="0 0 80 80" aria-hidden="true">
            <circle cx="40" cy="40" r="32" className="mp-diet-ring-bg" />
            <circle
              cx="40" cy="40" r="32"
              className={`mp-diet-ring-fg${left != null && left < 0 ? ' over' : ''}`}
              strokeDasharray={dash}
              strokeDashoffset={offset}
              transform="rotate(-90 40 40)"
            />
          </svg>
          <div className="mp-diet-ring-num">
            <b>{percent != null ? `${percent}%` : '-'}</b>
            <span>목표 대비</span>
          </div>
        </div>
        <div className="mp-diet-ring-caption">
          {kcal != null
            ? <>{kcal.toLocaleString()}{goal && ` / ${goal.toLocaleString()}`}kcal</>
            : '아직 오늘 기록이 없어요'}
        </div>
      </button>

      <div className="mp-diet-slots">
        {MEAL_SLOTS.map((type) => {
          const items = meals.filter((m) => m.meal_type === type)
          return (
            <div className={`mp-diet-slot${items.length ? '' : ' empty'}`} key={type}>
              <div className="mp-diet-slot-label">{MEAL_TYPE_LABEL[type]}</div>
              {items.length ? (
                <div className="mp-diet-slot-items">
                  {items.map((m) => (
                    <div className="mp-diet-slot-item" key={m.id}>{m.menu_name}</div>
                  ))}
                </div>
              ) : (
                <div className="mp-diet-slot-empty" aria-label="기록 없음">–</div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// 대표 지표(체중)는 항상 크게, 나머지 지표는 접어둔다 - 마이페이지에서 제일 자주 보는 건
// "지난번보다 빠졌나"지 다섯 개 숫자 전부가 아니다
function InbodyPanel({ inbody, history, aside, goalLabel, onEdit, onDelete }) {
  const [months, setMonths] = useState(3)
  const [detailOpen, setDetailOpen] = useState(false)

  const cutoff = months ? Date.now() - months * 30 * 24 * 3600 * 1000 : 0
  const inRange = history.filter((r) => new Date(r.measuredAt).getTime() >= cutoff)
  const pointsOf = (key) =>
    inRange.filter((r) => r[key] != null).map((r) => ({ t: new Date(r.measuredAt).getTime(), v: r[key] }))

  const heroPoints = pointsOf(HERO_METRIC.key)
  const heroValue = inbody[HERO_METRIC.key]
  const heroDelta = heroPoints.length >= 2 ? heroPoints[heroPoints.length - 1].v - heroPoints[0].v : null
  const periodLabel = months ? `${TREND_PERIODS.find((p) => p.months === months).label} 전` : '첫 기록'

  return (
    <>
      <div className="mp-overview">
        <div className="mp-hero">
          <div className="mp-hero-main">
            <div className="mp-hero-label">
              {HERO_METRIC.label}
              {goalLabel && <span className="mp-hero-goal">{goalLabel}</span>}
            </div>
            <div className="mp-hero-num">
              {heroValue != null ? heroValue : '-'}
              <small>{HERO_METRIC.unit}</small>
            </div>
            <div className="mp-hero-sub">
              {heroDelta != null ? (
                <>
                  {periodLabel} {heroPoints[0].v}{HERO_METRIC.unit} ·{' '}
                  <b className={heroDelta > 0 ? 'up' : heroDelta < 0 ? 'down' : ''}>
                    {heroDelta > 0 ? '+' : ''}{heroDelta.toFixed(1)}{HERO_METRIC.unit}
                  </b>
                </>
              ) : (
                `${measuredDate(inbody.measuredAt)} 측정`
              )}
            </div>
          </div>

          <div className="mp-hero-chart">
            <div className="mp-hero-head">
              
              {inbody.measuredAt && <span className="mp-measured-at">{measuredDate(inbody.measuredAt)} 측정</span>}
              {/* "다시 입력" 하나로 두 가지를 다 하고 있어서 뜻이 애매했다 - 새 측정을 추가하는
                  것과, 잘못 올린 사진을 바로잡는 것은 추이 그래프에 미치는 영향이 정반대라 나눈다 */}
              <span className="mp-hero-actions">
                <button className="link-btn" onClick={() => onEdit(false)}>새 측정 추가</button>
                <button className="link-btn" onClick={() => onEdit(true)}>이 기록 고치기</button>
                <button className="mp-hero-delete" onClick={onDelete}>삭제</button>
              </span>
            </div>
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
            {heroPoints.length >= 2 ? (
              <>
                <Sparkline points={heroPoints} area />
                <div className="mp-mini-axis">
                  {axisTicks(heroPoints).map((t) => (
                    <span key={t}>{shortDate(t)}</span>
                  ))}
                </div>
              </>
            ) : (
              <div className="mp-hero-empty">
                이 기간에는 기록이 {heroPoints.length}개예요. 두 번째 측정부터 그래프가 그려져요.
              </div>
            )}
          </div>
        </div>
        {aside}
      </div>

      <button
        className="mp-detail-toggle"
        onClick={() => setDetailOpen((o) => !o)}
        aria-expanded={detailOpen}
      >
        {detailOpen ? '접기' : '자세히 보기'}
        <span className={`mp-detail-caret${detailOpen ? ' open' : ''}`} aria-hidden="true">▾</span>
      </button>

      {detailOpen && (
        <div className="mp-trend-grid">
          {DETAIL_METRICS.map((m) => (
            <MiniTrend key={m.key} metric={m} points={pointsOf(m.key)} fallback={inbody[m.key]} />
          ))}
        </div>
      )}
    </>
  )
}

function InbodyUploadModal({ replaceLatest, onClose, onExtract, onConfirm }) {
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
      <div className="modal-backdrop">
        <div className="modal" onClick={(e) => e.stopPropagation()}>
          <button className="modal-close" onClick={onClose} aria-label="닫기">×</button>
          <div className="modal-title">인식 결과 확인</div>
          <div className="modal-sub">
            {replaceLatest
              ? '사진에서 읽은 값이 맞는지 확인해주세요. 저장하면 최근 기록이 이 값으로 바뀌어요'
              : '사진에서 읽은 값이 맞는지 확인해주세요. 저장하면 오늘 날짜로 새 기록이 추가돼요'}
          </div>

          <div className="modal-review-list">
            {INBODY_FIELDS.map(({ key, label, unit, step }) => (
              <div className="modal-review-item" key={key}>
                <span>{label}</span>
                <span className="modal-review-input-wrap">
                  <input
                    type="number"
                    min="0"
                    step={step}
                    className="modal-review-input"
                    placeholder="인식 안 됨"
                    value={extracted[key] ?? ''}
                    onChange={(e) => {
                      const v = e.target.value.replace(/-/g, '')
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
    <div className="modal-backdrop">
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose} aria-label="닫기">×</button>
        <div className="modal-title">{replaceLatest ? '이 기록 고치기' : '새 측정 추가'}</div>
        <div className="modal-sub">
          {replaceLatest
            ? '잘못 올린 사진을 바로잡아요. 새 기록이 생기지 않고 최근 기록이 교체됩니다'
            : '오늘 측정한 인바디 측정지 사진을 올려주세요. 추이 그래프에 점이 하나 늘어나요'}
        </div>

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
    <div className="modal-backdrop">
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
              min="0"
              step="0.1"
              className="modal-review-input"
              value={heightCm}
              onChange={(e) => setHeightCm(e.target.value.replace(/-/g, ''))}
            />
            <span className="modal-review-unit">cm</span>
          </span>
        </div>

        <div className="mp-body-field">
          <span className="mp-body-label">출생연도</span>
          <span className="modal-review-input-wrap">
            <input
              type="number"
              min="0"
              step="1"
              className="modal-review-input"
              value={birthYear}
              onChange={(e) => setBirthYear(e.target.value.replace(/-/g, ''))}
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
    <div className="modal-backdrop">
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
  const { user, profile, inbody, updateGoal, updateName, updateBody, extractInbody, confirmInbody, deleteInbody, getInbodyHistory, getTodayTotal, getTodayMeals, getNutrientTarget, deleteAccount } = useAuth()
  const navigate = useNavigate()
  const [inbodyHistory, setInbodyHistory] = useState([])
  const [bodyModalOpen, setBodyModalOpen] = useState(false)
  // null이면 닫힘. { replaceLatest } 를 담아서 "새 측정 추가"와 "이 기록 고치기"를 구분한다
  const [uploadMode, setUploadMode] = useState(null)
  const [editingName, setEditingName] = useState(false)
  const [nameDraft, setNameDraft] = useState('')
  const [nameError, setNameError] = useState('')
  const [todaySummary, setTodaySummary] = useState(null)
  const [todayMeals, setTodayMeals] = useState([])
  const [nutrientTarget, setNutrientTarget] = useState(null)
  const [nutrientModalOpen, setNutrientModalOpen] = useState(false)
  const [goalModalOpen, setGoalModalOpen] = useState(false)
  const [withdrawModalOpen, setWithdrawModalOpen] = useState(false)
  const [withdrawing, setWithdrawing] = useState(false)
  const [withdrawError, setWithdrawError] = useState('')
  const [firstInbodyGuide, setFirstInbodyGuide] = useState(false)
  const [deleteModalOpen, setDeleteModalOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState('')

  useEffect(() => {
    if (user) getTodayTotal(todayStr()).then(setTodaySummary).catch(() => {})
  }, [user, getTodayTotal])

  useEffect(() => {
    if (user) getTodayMeals(todayStr()).then(setTodayMeals).catch(() => {})
  }, [user, getTodayMeals])

  useEffect(() => {
    if (user) getNutrientTarget().then(setNutrientTarget).catch(() => {})
  }, [user, getNutrientTarget])

  // inbody(최신 레코드)가 바뀌면 = 새로 등록됐으면 추이도 다시 불러옴
  useEffect(() => {
    if (user) getInbodyHistory().then(setInbodyHistory).catch(() => {})
  }, [user, inbody, getInbodyHistory])

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
    const replaceLatest = Boolean(uploadMode?.replaceLatest)
    // 교체는 기록 수를 늘리지 않으므로 "첫 인바디가 등록됐어요" 안내 대상이 아니다
    const isFirst = !inbody && !replaceLatest
    return confirmInbody({ ...values, replaceLatest }).then((data) => {
      if (isFirst) setFirstInbodyGuide(true)
      return data
    })
  }

  const handleDeleteInbody = () => {
    setDeleting(true)
    setDeleteError('')
    deleteInbody(inbody.id)
      .then(() => setDeleteModalOpen(false))
      .catch((e) => setDeleteError(e.message || '삭제에 실패했어요'))
      .finally(() => setDeleting(false))
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
                  // onBlur로 저장하던 걸 뗐다 - 확인/취소 버튼을 누르는 순간 blur가 먼저 나서
                  // "취소를 눌렀는데 저장되는" 동작이 된다. 저장 시점은 버튼과 Enter로만 둔다.
                  <span className="mp-name-edit">
                    <input
                      className="mp-name-input"
                      value={nameDraft}
                      autoFocus
                      maxLength={50}
                      onChange={(e) => setNameDraft(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') submitName()
                        if (e.key === 'Escape') setEditingName(false)
                      }}
                    />
                    <button className="link-btn" onClick={submitName}>확인</button>
                    <button className="link-btn mp-name-cancel" onClick={() => setEditingName(false)}>취소</button>
                  </span>
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

          {inbody ? (
            <>
              <InbodyPanel
                inbody={inbody}
                history={inbodyHistory}
                goalLabel={GOAL_LABEL[profile?.goal]}
                onEdit={(replaceLatest) => setUploadMode({ replaceLatest })}
                onDelete={() => { setDeleteError(''); setDeleteModalOpen(true) }}
                aside={
                  <DietTodayCard
                    summary={todaySummary}
                    meals={todayMeals}
                    target={nutrientTarget}
                    onOpenDetail={() => setNutrientModalOpen(true)}
                  />
                }
              />

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
                {/* 기록이 하나도 없는 상태라 교체할 대상이 없다 - 항상 새 기록으로 추가 */}
                <button className="mp-inbody-btn" onClick={() => setUploadMode({ replaceLatest: false })}>
                  인바디 등록하기
                </button>
              </div>
            </div>
          )}

        </>
      ) : (
        <p className="pcard-desc">로그인 후 프로필을 확인할 수 있습니다.</p>
      )}

      {uploadMode && (
        <InbodyUploadModal
          replaceLatest={uploadMode.replaceLatest}
          onClose={() => setUploadMode(null)}
          onExtract={extractInbody}
          onConfirm={handleConfirmInbody}
        />
      )}
      {firstInbodyGuide && (
        <div className="modal-backdrop">
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <button className="modal-close" onClick={() => setFirstInbodyGuide(false)} aria-label="닫기">×</button>
            <div className="modal-title">첫 인바디가 등록됐어요</div>
            <div className="modal-sub">
              이제 체중·골격근량·체지방률을 기준으로 목표 칼로리가 계산돼요.
            </div>
            <p className="pcard-desc">
              변화 추이 그래프는 기록이 <strong>두 개 이상</strong>일 때부터 그려져요.
              다음에 인바디를 측정하면 "새 측정 추가"로 등록해주세요 — 그때부터 체중과 근육량이
              어떻게 변했는지 한눈에 볼 수 있어요.
            </p>
            <button className="modal-btn" onClick={() => setFirstInbodyGuide(false)}>확인했어요</button>
          </div>
        </div>
      )}
      {deleteModalOpen && (
        <div className="modal-backdrop">
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <button
              className="modal-close"
              onClick={() => setDeleteModalOpen(false)}
              disabled={deleting}
              aria-label="닫기"
            >
              ×
            </button>
            <div className="modal-title">이 기록을 삭제할까요?</div>
            <div className="modal-sub">
              {measuredDate(inbody?.measuredAt)} 측정 기록이 지워져요. 추이 그래프에서도 함께 빠집니다.
            </div>
            {deleteError && <p className="mp-name-error">{deleteError}</p>}
            <div className="modal-btn-row">
              <button
                className="modal-btn-secondary"
                onClick={() => setDeleteModalOpen(false)}
                disabled={deleting}
              >
                취소
              </button>
              <button className="modal-btn" onClick={handleDeleteInbody} disabled={deleting}>
                {deleting ? '삭제 중...' : '삭제하기'}
              </button>
            </div>
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
        <div className="modal-backdrop">
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

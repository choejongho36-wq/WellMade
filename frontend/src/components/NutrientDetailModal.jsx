import { useEffect, useState } from 'react'
import { getNutritionPeerCompare } from '../lib/aiApi.js'
import { useAuth } from '../lib/auth.js'
import Modal from './Modal.jsx'
import './NutrientDetailModal.css'

const HERO_GAUGE_SEGMENTS = 14
const MACRO_GAUGE_SEGMENTS = 7

const ROWS = [
  { key: 'totalCalories', targetKey: 'kcal', label: '총 섭취 칼로리', short: '칼로리', unit: 'kcal' },
  { key: 'totalProteinG', targetKey: 'proteinG', label: '단백질', unit: 'g' },
  { key: 'totalCarbsG', targetKey: 'carbsG', label: '탄수화물', unit: 'g' },
  { key: 'totalFatG', targetKey: 'fatG', label: '지방', unit: 'g' },
]
const MACRO_ROWS = ROWS.slice(1)

function formatValue(value, unit) {
  return unit === 'kcal' ? Math.round(value) : value.toFixed(1)
}

function gaugeFilledCount(value, targetValue, segments) {
  if (targetValue == null || targetValue <= 0) return 0
  const percent = Math.min(100, (value / targetValue) * 100)
  return Math.round((percent / 100) * segments)
}

/** 목표를 넘겼는지 - 목표가 없거나 0이면 판정하지 않음 */
function isOver(value, targetValue) {
  return targetValue != null && targetValue > 0 && value > targetValue
}

/** 초과 섭취 표시용 화살표 (위로 통통 튀는 애니메이션은 CSS에서) */
function OverArrow() {
  return <span className="nutrient-over-arrow" aria-hidden="true">▲</span>
}

function Gauge({ filled, total, tone }) {
  // 모달이 열릴 때 0에서 시작해서 실제 값까지 순서대로 차오르는 효과를 주기 위해,
  // 마운트 직후 한 프레임 뒤에 실제 filled 값으로 올림 (CSS transition-delay가 나머지를 처리)
  const [animatedFilled, setAnimatedFilled] = useState(0)

  useEffect(() => {
    const raf = requestAnimationFrame(() => setAnimatedFilled(filled))
    return () => cancelAnimationFrame(raf)
  }, [filled])

  return (
    <div className="nutrient-gauge">
      {Array.from({ length: total }, (_, i) => (
        <div
          key={i}
          className={`nutrient-gauge-seg ${tone}${i < animatedFilled ? ' filled' : ''}`}
          style={{ transitionDelay: `${i * 25}ms` }}
        />
      ))}
    </div>
  )
}

function MacroColumn({ label, unit, value, targetValue }) {
  const displayValue = formatValue(value, unit)
  const filled = gaugeFilledCount(value, targetValue, MACRO_GAUGE_SEGMENTS)
  const over = isOver(value, targetValue)

  return (
    <div className="nutrient-macro-col">
      <div className={`nutrient-macro-label${over ? ' over' : ''}`}>
        {label}{over && <OverArrow />}
      </div>
      <div className="nutrient-macro-values">
        <span className="nutrient-macro-value">{displayValue}{unit}</span>
        {targetValue != null && (
          <span className="nutrient-macro-target">{Math.round(targetValue)}{unit}</span>
        )}
      </div>
      {targetValue != null && <Gauge filled={filled} total={MACRO_GAUGE_SEGMENTS} tone="dark" />}
    </div>
  )
}

function TargetEditForm({ target, onSaved, onCancel }) {
  const { updateNutrientTarget, resetNutrientTarget } = useAuth()
  const [draft, setDraft] = useState({
    kcal: String(Math.round(target.kcal)),
    proteinG: String(Math.round(target.proteinG)),
    carbsG: String(Math.round(target.carbsG)),
    fatG: String(Math.round(target.fatG)),
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const setField = (field) => (e) => setDraft((d) => ({ ...d, [field]: e.target.value.replace(/-/g, '') }))

  const handleSave = () => {
    const parsed = {
      kcal: Number(draft.kcal),
      proteinG: Number(draft.proteinG),
      carbsG: Number(draft.carbsG),
      fatG: Number(draft.fatG),
    }
    if (Object.values(parsed).some((v) => !Number.isFinite(v) || v < 0)) {
      setError('0 이상의 숫자를 입력해주세요')
      return
    }
    setSaving(true)
    setError('')
    updateNutrientTarget(parsed)
      .then(onSaved)
      .catch((e) => setError(e.message || '저장에 실패했어요'))
      .finally(() => setSaving(false))
  }

  const handleReset = () => {
    setSaving(true)
    setError('')
    resetNutrientTarget()
      .then(onSaved)
      .catch((e) => setError(e.message || '초기화에 실패했어요'))
      .finally(() => setSaving(false))
  }

  return (
    <div className="nutrient-target-form">
      {ROWS.map(({ targetKey, label, unit }) => (
        <label className="nutrient-target-field" key={targetKey}>
          <span>{label}</span>
          <span className="nutrient-target-input-wrap">
            <input
              type="number"
              min="0"
              value={draft[targetKey]}
              onChange={setField(targetKey)}
              disabled={saving}
            />
            <span className="nutrient-target-unit">{unit}</span>
          </span>
        </label>
      ))}
      {error && <p className="nutrient-target-error">{error}</p>}
      <div className="nutrient-target-actions">
        {target.custom && (
          <button className="modal-btn-secondary nutrient-target-reset" onClick={handleReset} disabled={saving}>
            추천값으로 초기화
          </button>
        )}
        <div className="nutrient-target-actions-row">
          <button className="modal-btn-secondary" onClick={onCancel} disabled={saving}>취소</button>
          <button className="modal-btn" onClick={handleSave} disabled={saving}>
            {saving ? '저장 중...' : '저장'}
          </button>
        </div>
      </div>
    </div>
  )
}

function NutrientDetailModal({ summary, target, onClose, onTargetChange, title = '오늘 영양소' }) {
  const { profile } = useAuth()
  const [editing, setEditing] = useState(false)
  const [peer, setPeer] = useState(null)

  // 같은 성별·연령대 평균과 비교(AI 서버). 프로필이 없거나 AI 서버가 꺼져 있으면
  // null이 와서 아래 섹션이 안 보일 뿐, 영양소 화면 자체는 그대로 동작한다
  useEffect(() => {
    getNutritionPeerCompare({
      total: summary,
      gender: profile?.gender,
      birthYear: profile?.birthYear,
    }).then(setPeer)
  }, [summary, profile?.gender, profile?.birthYear])

  const handleSaved = (newTarget) => {
    onTargetChange?.(newTarget)
    setEditing(false)
  }

  const calories = summary.totalCalories ?? 0
  const targetKcal = target ? target.kcal : null
  const heroFilled = gaugeFilledCount(calories, targetKcal, HERO_GAUGE_SEGMENTS)
  const overLabels = target
    ? ROWS.filter((r) => isOver(summary[r.key] ?? 0, target[r.targetKey])).map((r) => r.short ?? r.label)
    : []

  return (
    <Modal className="nutrient-modal" onClose={onClose}>
        <div className="modal-title">{title}</div>

        {editing ? (
          <div className="nutrient-edit-wrap">
            <TargetEditForm target={target} onSaved={handleSaved} onCancel={() => setEditing(false)} />
          </div>
        ) : (
          <>
            <div className="nutrient-hero">
              <div className="nutrient-hero-top">
                <div className="nutrient-hero-label">
                  총 섭취 칼로리{isOver(calories, targetKcal) && <OverArrow />}
                </div>
                {target && (
                  <button className="nutrient-target-edit" onClick={() => setEditing(true)}>목표 수정</button>
                )}
              </div>
              <div className="nutrient-hero-values">
                <div className="nutrient-hero-value">
                  <span className="nutrient-hero-num">{Math.round(calories)}</span>
                  <span className="nutrient-hero-unit">kcal</span>
                </div>
                {targetKcal != null && (
                  <div className="nutrient-hero-target">
                    <div className="nutrient-hero-target-label">목표</div>
                    <div className="nutrient-hero-target-value">{Math.round(targetKcal)}kcal</div>
                  </div>
                )}
              </div>
              {targetKcal != null && <Gauge filled={heroFilled} total={HERO_GAUGE_SEGMENTS} tone="light" />}
            </div>

            <div className="nutrient-macros">
              {MACRO_ROWS.map(({ key, targetKey, label, unit }) => (
                <MacroColumn
                  key={key}
                  label={label}
                  unit={unit}
                  value={summary[key] ?? 0}
                  targetValue={target ? target[targetKey] : null}
                />
              ))}
            </div>

            {overLabels.length > 0 && (
              <p className="nutrient-over-warning">
                <OverArrow />
                초과 섭취 주의 · {overLabels.join(', ')} — 목표치를 넘었어요
              </p>
            )}

            {/* 또래 비교 - 목표 대비(위 게이지)와 다른 축의 정보다.
                목표를 안 정한 사용자에게도 "많이 먹었나 적게 먹었나" 감각을 준다 */}
            {peer && peer.comparisons.length > 0 && (
              <div className="nutrient-peer">
                <div className="nutrient-peer-head">
                  같은 {peer.age_bracket}세 평균과 비교
                  {peer.low_sample_warning && ' (표본이 적어 참고용)'}
                </div>
                {peer.comparisons.map((c) => (
                  <div className="nutrient-peer-row" key={c.nutrient}>
                    <span className="nutrient-peer-label">{c.nutrient}</span>
                    <span className="nutrient-peer-value">
                      {c.my_value}{c.unit} <span className="nutrient-peer-mean">/ 평균 {c.peer_mean}{c.unit}</span>
                    </span>
                    <span className="nutrient-peer-pct">{c.percent_of_peer}%</span>
                  </div>
                ))}
                <div className="nutrient-peer-source">{peer.source}</div>
              </div>
            )}

            {!target && (
              <p className="nutrient-no-target">
                목표와 인바디를 등록하면 목표 대비 섭취량을 함께 볼 수 있어요.
              </p>
            )}
          </>
        )}
    </Modal>
  )
}

export default NutrientDetailModal

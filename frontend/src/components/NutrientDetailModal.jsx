import { useState } from 'react'
import { useAuth } from '../lib/auth.js'
import './NutrientDetailModal.css'

const HERO_GAUGE_SEGMENTS = 14
const MACRO_GAUGE_SEGMENTS = 7

const ROWS = [
  { key: 'totalCalories', targetKey: 'kcal', label: '총 섭취 칼로리', unit: 'kcal' },
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

function Gauge({ filled, total, tone }) {
  return (
    <div className="nutrient-gauge">
      {Array.from({ length: total }, (_, i) => (
        <div key={i} className={`nutrient-gauge-seg ${tone}${i < filled ? ' filled' : ''}`} />
      ))}
    </div>
  )
}

function MacroColumn({ label, unit, value, targetValue }) {
  const displayValue = formatValue(value, unit)
  const filled = gaugeFilledCount(value, targetValue, MACRO_GAUGE_SEGMENTS)

  return (
    <div className="nutrient-macro-col">
      <div className="nutrient-macro-label">{label}</div>
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

  const setField = (field) => (e) => setDraft((d) => ({ ...d, [field]: e.target.value }))

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
  const [editing, setEditing] = useState(false)

  const handleSaved = (newTarget) => {
    onTargetChange?.(newTarget)
    setEditing(false)
  }

  const calories = summary.totalCalories ?? 0
  const targetKcal = target ? target.kcal : null
  const heroFilled = gaugeFilledCount(calories, targetKcal, HERO_GAUGE_SEGMENTS)

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal nutrient-modal" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose} aria-label="닫기">×</button>

        <div className="nutrient-modal-head">
          <div className="modal-title">{title}</div>
          {target && !editing && (
            <button className="link-btn" onClick={() => setEditing(true)}>목표 수정</button>
          )}
        </div>

        {editing ? (
          <div className="nutrient-edit-wrap">
            <TargetEditForm target={target} onSaved={handleSaved} onCancel={() => setEditing(false)} />
          </div>
        ) : (
          <>
            <div className="nutrient-hero">
              <div className="nutrient-hero-label">총 섭취 칼로리</div>
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

            {!target && (
              <p className="nutrient-no-target">
                목표와 인바디를 등록하면 목표 대비 섭취량을 함께 볼 수 있어요.
              </p>
            )}
          </>
        )}
      </div>
    </div>
  )
}

export default NutrientDetailModal

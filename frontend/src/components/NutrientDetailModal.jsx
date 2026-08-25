import './NutrientDetailModal.css'

const CAL_PER_G = { totalProteinG: 4, totalCarbsG: 4, totalFatG: 9 }

const ROWS = [
  { key: 'totalProteinG', label: '단백질', unit: 'g' },
  { key: 'totalCarbsG', label: '탄수화물', unit: 'g' },
  { key: 'totalFatG', label: '지방', unit: 'g' },
]

function NutrientDetailModal({ summary, onClose }) {
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal nutrient-modal" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose} aria-label="닫기">×</button>
        <div className="modal-title">오늘 영양소</div>
        <div className="modal-sub">칼로리 {Math.round(summary.totalCalories)}kcal 기준</div>

        <div className="nutrient-list">
          {ROWS.map(({ key, label, unit }) => {
            const value = summary[key] ?? 0
            const kcalFromMacro = value * CAL_PER_G[key]
            const percent = summary.totalCalories > 0
              ? Math.min(100, Math.round((kcalFromMacro / summary.totalCalories) * 100))
              : 0
            return (
              <div className="nutrient-row" key={key}>
                <div className="nutrient-row-head">
                  <span className="nutrient-row-label">{label}</span>
                  <span className="nutrient-row-value">{value.toFixed(1)}{unit}</span>
                </div>
                <div className="nutrient-bar">
                  <div className="nutrient-bar-fill" style={{ width: `${percent}%` }} />
                </div>
                <div className="nutrient-row-percent">칼로리의 {percent}%</div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

export default NutrientDetailModal

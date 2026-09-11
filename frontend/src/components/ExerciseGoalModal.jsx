import { useState } from 'react'
import { EXERCISE_OPTIONS } from '../lib/exerciseGoals.js'
import './ExerciseGoalModal.css'

/**
 * 운동별(스쿼트 등) 하루 목표 횟수를 설정하는 모달 — "신체 정보" 모달(BodyInfoModal)과
 * 같은 디자인 패턴을 쓴다. exerciseGoals.js 참고. 지금은 스쿼트만 실제로 코칭·집계되므로,
 * 런지·플랭크는 드롭다운에 "(개발중)"으로 표시하고 목표 숫자만 저장될 뿐 리포트/달력에는
 * 반영되지 않는다(추후 실제로 붙으면 그때 연결).
 *
 * (2026-09-09) 원래 MyPage.jsx 전용이었는데, 코칭 페이지(SquatCoachingPage.jsx)의 "카메라
 * 켜고 시작하기" 버튼에서도 목표 미설정 시 이 모달을 띄워야 해서 공용 컴포넌트로 뺐다.
 * 저장은 여기서 직접 하지 않고(onSave 콜백에 정리된 배열만 넘김) 호출부가
 * saveExerciseGoals()를 부르는 방식은 그대로다 — 마이페이지든 코칭 페이지든 같은
 * localStorage(wellmade_exercise_goals)에 저장하므로, 어느 화면에서 설정해도 마이페이지에
 * 그대로 반영된다.
 */
function ExerciseGoalModal({ goals, onClose, onSave }) {
  const [rows, setRows] = useState(
    goals.length > 0
      ? goals.map((g) => ({
          id: g.id,
          targetReps: g.targetReps,
          targetSets: g.targetSets ?? 1,
          deepSquatMode: Boolean(g.deepSquatMode),
        }))
      : [{ id: 'squat', targetReps: 20, targetSets: 1, deepSquatMode: false }],
  )
  const [saving, setSaving] = useState(false)

  const updateRow = (idx, patch) => {
    setRows((rs) => rs.map((r, i) => (i === idx ? { ...r, ...patch } : r)))
  }
  const removeRow = (idx) => {
    setRows((rs) => rs.filter((_, i) => i !== idx))
  }
  const addRow = () => {
    const used = new Set(rows.map((r) => r.id))
    const next = EXERCISE_OPTIONS.find((o) => !used.has(o.id))
    if (!next) return
    setRows((rs) => [...rs, { id: next.id, targetReps: 20, targetSets: 1, deepSquatMode: false }])
  }

  const handleSave = () => {
    setSaving(true)
    const cleaned = rows.map((r) => ({
      id: r.id,
      name: EXERCISE_OPTIONS.find((o) => o.id === r.id)?.label ?? r.id,
      targetReps: Math.max(0, Math.min(999, Number(r.targetReps) || 0)),
      targetSets: Math.max(1, Math.min(20, Number(r.targetSets) || 1)),
      deepSquatMode: Boolean(r.deepSquatMode),
    }))
    onSave(cleaned)
    setSaving(false)
    onClose()
  }

  return (
    <div className="modal-backdrop">
      <div className="modal mp-goal-modal-wide" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose} aria-label="닫기">×</button>
        <div className="modal-title">운동 목표</div>
        <div className="modal-sub">
          운동별 하루 목표 횟수를 정해두면, 스쿼트 코칭 리포트·달력에서 목표를 채운 날을 확인할 수
          있어요.
        </div>

        {rows.map((row, idx) => (
          <div key={idx} className="mp-goal-modal-row">
            <select
              className="mp-goal-select-input"
              value={row.id}
              onChange={(e) => updateRow(idx, { id: e.target.value })}
            >
              {EXERCISE_OPTIONS.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.label}
                  {o.devInProgress ? ' (개발중)' : ''}
                </option>
              ))}
            </select>
            <span className="modal-review-input-wrap">
              <input
                type="number"
                min="0"
                max="999"
                className="modal-review-input"
                value={row.targetReps}
                onChange={(e) => updateRow(idx, { targetReps: e.target.value })}
              />
              <span className="modal-review-unit">회</span>
            </span>
            <span className="modal-review-input-wrap">
              <input
                type="number"
                min="1"
                max="20"
                className="modal-review-input"
                value={row.targetSets}
                onChange={(e) => updateRow(idx, { targetSets: e.target.value })}
              />
              <span className="modal-review-unit">세트/일</span>
            </span>
            {rows.length > 1 && (
              <button type="button" className="link-btn mp-goal-remove" onClick={() => removeRow(idx)}>
                삭제
              </button>
            )}
          </div>
        ))}

        {rows.map((row, idx) =>
          row.id === 'squat' ? (
            <label key={`deep-${idx}`} className="mp-goal-deep-squat-row">
              <input
                type="checkbox"
                checked={row.deepSquatMode}
                onChange={(e) => updateRow(idx, { deepSquatMode: e.target.checked })}
              />
              깊게(ATG) 스쿼트해요 — 무릎 깊이 제한 풀기
            </label>
          ) : null,
        )}

        {rows.length < EXERCISE_OPTIONS.length && (
          <button type="button" className="link-btn mp-goal-add-link" onClick={addRow}>
            + 운동 추가
          </button>
        )}

        <button className="modal-btn" onClick={handleSave} disabled={saving} style={{ marginTop: 16 }}>
          {saving ? '저장 중...' : '저장하기'}
        </button>
      </div>
    </div>
  )
}

export default ExerciseGoalModal

import { Link } from 'react-router-dom'
import './RecentSessionsList.css'

const WEEKDAY_KO = ['일', '월', '화', '수', '목', '금', '토']

// 세션 이력의 날짜(YYYY-MM-DD)를 "2026.09.08 (화)" 형태로 바꾼다.
export function formatDateWithWeekday(dateStr) {
  const d = new Date(`${dateStr}T00:00:00`)
  const [y, m, day] = dateStr.split('-')
  return `${y}.${m}.${day} (${WEEKDAY_KO[d.getDay()]})`
}

function formatMinutes(sec) {
  if (sec == null) return '-'
  return `${Math.max(1, Math.round(sec / 60))}분`
}

// 세션 하나의 "점수" — score 필드가 있으면 그대로 쓰고, 없으면(이번 업데이트 전에 저장된
// 옛 기록이라 score/reps/durationSec가 없는 경우) 정상 자세 비율로 대체 계산한다
// (하위 호환, squatSessionHistory.js 참고 — 저장 형태 자체는 그대로 두고 프론트에서만
// 안전하게 읽는다).
export function sessionScore(entry) {
  if (entry.score != null) return entry.score
  return Math.round((entry.normal_ratio ?? 0) * 100)
}

/**
 * 최근 세션 이력을 카드 리스트로 보여준다(2026-09-09 추가) — 실시간 코칭 화면의 달력
 * 모달과 운동 기록 페이지(ExerciseHistoryPage) 양쪽에서 재사용한다.
 *
 * onSelect가 있으면(운동 기록 페이지) 각 행이 버튼이 되어 그 날짜를 선택하고,
 * moreTo가 있으면(달력 모달) 우측 상단에 "더보기" 링크가 붙어 운동 기록 페이지로
 * 이동한다. 둘 다 없어도(단순 목록) 동작하도록 짰다.
 */
function RecentSessionsList({ sessions, limit, onSelect, selectedDate, moreTo, title = '최근 세션' }) {
  const items = limit != null ? sessions.slice(0, limit) : sessions

  return (
    <div className="recent-sessions-card">
      <div className="recent-sessions-header">
        <span className="recent-sessions-title">{title}</span>
        {moreTo && (
          <Link to={moreTo} className="recent-sessions-more">더보기 ›</Link>
        )}
      </div>
      {items.length === 0 ? (
        <p className="recent-sessions-empty">아직 운동 기록이 없어요.</p>
      ) : (
        <div className="recent-sessions-rows">
          {items.map((entry, i) => {
            const score = sessionScore(entry)
            const isGood = score >= 80
            const isSelected = onSelect != null && selectedDate === entry.date
            const Row = onSelect ? 'button' : 'div'
            return (
              <Row
                key={`${entry.date}-${i}`}
                type={onSelect ? 'button' : undefined}
                className={`recent-session-row${onSelect ? ' is-clickable' : ''}${isSelected ? ' is-selected' : ''}`}
                onClick={onSelect ? () => onSelect(entry.date) : undefined}
              >
                <div className="recent-session-info">
                  <div className="recent-session-date">{formatDateWithWeekday(entry.date)}</div>
                  <div className="recent-session-sub">
                    스쿼트 {entry.reps ?? '-'}회 · {formatMinutes(entry.durationSec)}
                  </div>
                </div>
                <span className={`recent-session-score${isGood ? ' is-good' : ' is-ok'}`}>{score}점</span>
                {onSelect && <span className="recent-session-chevron">›</span>}
              </Row>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default RecentSessionsList

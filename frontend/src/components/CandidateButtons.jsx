/**
 * 매칭 후보 선택 칩. 지금 매칭된 이름(searchName)도 목록 안에 포함해서 레드로 채워 보여주고,
 * 나머지 후보는 아웃라인으로 - "지금 뭐가 선택돼있는지"가 목록 밖 설명 없이 바로 읽힌다.
 * 기록 직후 모달과 타임라인 항목 두 곳에서 같이 씀.
 */
export function otherCandidates(item) {
  return (item.candidates ?? []).filter((c) => c !== item.searchName)
}

function CandidateButtons({ item, onPick, changing }) {
  if (otherCandidates(item).length === 0) return null

  return (
    <div className="diet-item-candidates">
      {(item.candidates ?? []).map((candidate) => {
        const selected = candidate === item.searchName
        return (
          <button
            key={candidate}
            className={`diet-item-candidate-chip${selected ? ' selected' : ''}`}
            onClick={() => onPick(candidate)}
            disabled={changing || selected}
          >
            <span className="diet-item-candidate-dot" aria-hidden="true" />
            {changing && !selected ? '변경 중...' : candidate}
          </button>
        )
      })}
    </div>
  )
}

export default CandidateButtons

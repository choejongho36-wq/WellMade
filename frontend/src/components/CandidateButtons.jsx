/**
 * 매칭 후보 버튼 목록. 기록 직후 모달과 타임라인 항목 두 곳에서 같이 씀.
 * 지금 매칭된 이름(currentName)은 빼고 보여준다 - 같은 걸 다시 고르는 버튼은 의미가 없어서.
 */
export function otherCandidates(item) {
  return (item.candidates ?? []).filter((c) => c !== item.searchName)
}

function CandidateButtons({ item, onPick, changing }) {
  const others = otherCandidates(item)
  if (others.length === 0) return null

  return (
    <div className="diet-item-candidates">
      {others.map((candidate) => (
        <button
          key={candidate}
          className="diet-item-candidate-btn"
          onClick={() => onPick(candidate)}
          disabled={changing}
        >
          {changing ? '변경 중...' : candidate}
        </button>
      ))}
    </div>
  )
}

export default CandidateButtons

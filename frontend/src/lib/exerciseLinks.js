/**
 * 챗봇 답변 본문에서 "어디까지가 운동 이름인가"를 찾는 부분.
 *
 * 그리는 쪽(ChatDrawer)과 분리해 둔 이유는 이 판단이 문자열 규칙 덩어리이기 때문이다 -
 * 조사가 붙고("덤벨 스쿼트를"), 짧은 이름이 긴 이름 안에 들어 있고("푸시업" ⊂ "닐링 푸시업"),
 * 모델이 띄어쓰기를 바꿔 쓴다("덤벨스쿼트"). React 없이 이 규칙만 따로 확인할 수 있어야 한다.
 */

function escapeRegExp(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/**
 * 본문에서 링크로 감쌀 구간을 찾는다. [{ start, end, link }] 를 시작 위치 순으로 돌려준다.
 *
 * - 긴 이름부터 찾는다. "푸시업"이 먼저 자리를 차지하면 "닐링 푸시업"이 반쪽만 링크된다.
 * - 한국어는 조사가 이름에 바로 붙어서 단어 경계 정규식을 쓸 수 없다. 그래서 이미 다른 이름이
 *   차지한 구간을 건너뛰는 방식으로 겹침을 막는다(AI 서버의 names_in_text와 같은 방식).
 * - 이름 안의 공백은 \s* 로 둬서 모델이 붙여 쓴 경우도 잡는다.
 * - 한 운동당 처음 나온 한 곳만 링크한다. 나올 때마다 링크하면 본문이 링크 밭이 된다.
 *
 * @param {string} text  답변 본문
 * @param {Array<{exercise?: string, url: string, label?: string}>} links 서버가 실어 보낸 영상
 */
export function findExerciseSpans(text, links) {
  if (typeof text !== 'string' || !links?.length) return []

  const ordered = [...links].sort((a, b) => (b.exercise || '').length - (a.exercise || '').length)
  const found = []
  for (const link of ordered) {
    const name = (link.exercise || '').trim()
    if (!name) continue
    const pattern = name.split(/\s+/).map(escapeRegExp).join('\\s*')
    for (const match of text.matchAll(new RegExp(pattern, 'g'))) {
      const start = match.index
      const end = start + match[0].length
      if (found.some((f) => start < f.end && end > f.start)) continue
      found.push({ start, end, link })
      break
    }
  }
  return found.sort((a, b) => a.start - b.start)
}

/**
 * 본문에서 링크가 안 붙은 영상만 남긴다(말풍선 아래 버튼용).
 *
 * 모델이 이름을 바꿔 쓰거나 목록을 줄여 쓰는 턴이 있어서 버튼 경로를 남겨 둔다 - 없애면
 * 그런 턴에서 영상이 통째로 사라진다. 같은 영상이 여러 운동에 붙을 수 있으므로(잭 점프 /
 * 스타 점프 -> 같은 점핑잭 영상) 주소로 중복을 없앤다.
 */
export function leftoverLinks(links, usedUrls) {
  const seen = new Set(usedUrls)
  return (links || []).filter((link) => (link.url && !seen.has(link.url) ? seen.add(link.url) : false))
}

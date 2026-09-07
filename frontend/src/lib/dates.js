/**
 * "오늘"의 기준을 한국 시간으로 고정한다.
 *
 * 예전엔 화면마다 `new Date()`로 오늘을 구했는데, 그건 브라우저가 있는 시간대 기준이다.
 * 서버는 KST로 미래 날짜를 막으므로(AppTime), 기기 시간대가 다르면 달력에서 고른 "오늘"이
 * 서버에서 "미래 날짜"로 거절되거나 어제로 기록될 수 있다. 판단 기준을 한쪽으로 맞춘다.
 */
const KST_FORMATTER = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Seoul',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
})

/** 한국 시간 기준 오늘 (yyyy-MM-dd) - en-CA 로캘이 그대로 이 형식을 준다 */
export function todayStr() {
  return KST_FORMATTER.format(new Date())
}

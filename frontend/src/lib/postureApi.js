/**
 * 정지 자세 분석 서버(posture-ai) 호출 헬퍼.
 *
 * aiApi.js와 분리한 이유: aiApi.js는 운동 동작 코칭 서버(ai, :8000)를 부르고
 * 여기는 정지 자세 서버(posture-ai, :8001)를 부른다. 두 서버는 주소도 응답
 * 형태도 달라서 섞으면 "이 함수는 어느 서버를 부르는가"가 흐려진다 —
 * aiApi.js가 auth.js와 분리된 것과 같은 이유다.
 *
 * 사진은 보내지 않는다. 브라우저가 MediaPipe로 뽑은 좌표(33개)만 보내므로
 * 신체 사진이 사용자 기기를 벗어나지 않는다. 전송량도 수 MB에서 수 KB로 준다.
 */

/**
 * 기본값이 빈 문자열인 이유:
 *   프로덕션에서는 nginx가 /posture/ 를 posture-ai:8001 로 프록시하므로
 *   프론트와 같은 오리진이 된다(nginx.conf 참고). 빈 값이면 요청이
 *   "/posture/analyze/..." 상대 경로로 나가 CORS가 발생하지 않는다.
 *
 *   로컬 개발에서는 vite dev server(:5173)와 posture-ai(:8001)가 다른
 *   포트라 .env.local 에 VITE_POSTURE_AI_BASE=http://localhost:8001 을
 *   넣어야 한다(팀 VITE_AI_BASE 와 같은 방식). 이때는 posture-ai 서버의
 *   CORS 설정이 요청을 허용한다.
 */
export const POSTURE_AI_BASE = import.meta.env.VITE_POSTURE_AI_BASE || ''

/**
 * 정지 자세를 분석한다.
 *
 * @param {'front'|'side'} view  정면(어깨·골반 좌우 기울기) / 측면(전방머리자세·라운드숄더)
 * @param {Array<{x:number,y:number,z:number,visibility:number}>} landmarks
 *        MediaPipe Pose 33개 좌표. usePoseLandmarker의 detectPose()가 주는 형태 그대로.
 * @param {number} imageWidth   원본 사진 가로 픽셀 (img.naturalWidth)
 * @param {number} imageHeight  원본 사진 세로 픽셀 (img.naturalHeight)
 *
 * imageWidth/Height를 함께 보내는 이유: MediaPipe는 x를 너비 대비, y를 높이
 * 대비로 각각 따로 정규화해서, 정사각형이 아닌 사진에서는 두 축의 실제
 * 스케일이 다르다. 서버가 종횡비를 보정하지 않으면 각도가 왜곡된다
 * (실측: 720x900 사진에서 약 6도 차이).
 */
export async function analyzePosture(view, landmarks, imageWidth, imageHeight) {
  const res = await fetch(`${POSTURE_AI_BASE}/posture/analyze/${view}/agent`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      landmarks,
      image_width: imageWidth,
      image_height: imageHeight,
    }),
  })

  if (!res.ok) {
    // 422는 좌표 형식이 어긋난 경우(개수 부족 등) — 사용자에게는 재시도를
    // 안내하고, 콘솔에 원본 사유를 남겨 디버깅할 수 있게 한다.
    let detail = ''
    try {
      detail = JSON.stringify(await res.json())
    } catch {
      detail = res.statusText
    }
    console.error('[posture-ai]', res.status, detail)
    throw new Error(
      res.status === 422
        ? '사진에서 자세를 제대로 읽지 못했어요. 다시 촬영해 주세요.'
        : '자세 분석 서버와 통신하지 못했어요. 잠시 후 다시 시도해 주세요.',
    )
  }

  return res.json()
}

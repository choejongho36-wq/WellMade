# posture-ai — 정지 자세 분석 서버

서 있는 자세(정면/측면 사진)를 분석해 어깨·골반 좌우 기울기, 전방머리자세,
라운드숄더를 판정하고 자연어 설명을 생성한다.

팀 `ai/` 서버(운동 동작 코칭)와는 **별개 서비스**다. 같은 프로젝트 안에
있지만 의존성·포트·배포를 분리했다:

- 서로의 `requirements.txt`가 섞이지 않는다 (한쪽 변경이 다른 쪽 배포에 영향 없음)
- 한쪽이 죽어도 다른 쪽은 계속 동작한다
- 저장소의 `ai/` `backend/` `frontend/` 구조와 같은 패턴이다

| | `ai/` (팀) | `posture-ai/` (이 서버) |
|---|---|---|
| 대상 | 운동 동작 (스쿼트 등) | 정지 자세 (서 있는 자세) |
| 포트 | 8000 | 8001 |
| LLM | AWS Bedrock (boto3) | Anthropic (tool-use 에이전트) |

---

## 설계 원칙

**서버는 자세추정을 하지 않는다.** 브라우저(`@mediapipe/tasks-vision`)가
좌표를 뽑아 보내면 서버는 그 숫자만 받아 판정한다. 팀 `ai/` 서버와 같은
원칙이며, 두 가지 이점이 있다:

1. **신체 사진이 서버에 도달하지 않는다** — 전송·로그·크래시덤프 어디에도
   남지 않는다. 자세 사진은 민감도가 높은 편이라 이 차이가 크다.
2. `mediapipe`(~100MB) 의존성이 빠져 배포 이미지가 가볍다.

이 전환이 결과를 바꾸지 않는다는 것은 실측으로 확인했다
(`posture-mvp/scripts/verify_landmark_input.py`) — 같은 사진을 이미지 입력과
좌표 입력 두 경로로 돌렸을 때 각도·판정·quality·reliability가 **완전히
동일**했다. 유일한 차이는 세그멘테이션 교차검증(`person_detection`)이
빠지면서 등급이 "강함"에서 "보통"으로 내려가는 것인데, 이 등급은 원래
`is_reliable`을 떨어뜨리지 않는다(`quality.assess_combined_reliability`는
"약함"만 문제로 본다). 마네킹 방어도 유지된다 — 그건 세그멘테이션이 아니라
`check_geometric_plausibility`(어깨/골반이 겹쳐 찍히는 것)가 담당한다.

**판단은 LLM, 계산은 코드.** 각도와 3단계 판정은 전부 코드가 확정하고,
LLM은 그 결과를 설명하는 문구만 만든다. 이를 구조적으로 강제하기 위해:
계산 함수를 에이전트 도구로 노출하지 않고, 도구 출력에서 측정 수치를
제거하며, LLM 출력에 숫자가 있으면 기계적으로 거부하고 폴백한다.

---

## 실행

```bash
pip install -r requirements.txt
cp .env.example .env          # ANTHROPIC_API_KEY 기입 (없어도 동작)
uvicorn app.main:app --reload --port 8001
```

키가 없으면 코멘트만 결정론적 템플릿 문구로 대체되고
(`comment.source == "fallback"`), 각도·판정은 그대로 나온다.

### 테스트

```bash
python -m pytest -q      # 155개
```

MediaPipe 모델 파일이 필요 없어 CI에서 바로 돌아간다.

---

## API

| 엔드포인트 | 설명 |
|---|---|
| `POST /posture/analyze/front` | 정면: 어깨·골반 좌우 기울기 |
| `POST /posture/analyze/side` | 측면: 전방머리자세·라운드숄더 |
| `POST /posture/analyze/front/agent` | 정면 + 에이전트 코멘트 |
| `POST /posture/analyze/side/agent` | 측면 + 에이전트 코멘트 |
| `GET /health` | 상태 확인 |

`/agent` 경로를 따로 둔 이유는 기존 경로의 응답이 바뀌지 않도록 잠그기
위해서다 — 옵션 플래그로 섞으면 회귀를 테스트로 확인하기 어렵다.

### 요청

```json
{
  "landmarks": [
    {"x": 0.4673, "y": 0.1172, "z": -0.4396, "visibility": 1.0},
    ... 33개 (MediaPipe Pose 인덱스 순서 그대로)
  ],
  "image_width": 720,
  "image_height": 900
}
```

`image_width`/`image_height`가 필요한 이유: MediaPipe는 x를 너비 대비,
y를 높이 대비로 각각 따로 정규화한다. 정사각형이 아닌 사진에서 두 축의
물리적 스케일이 달라지므로, 정규화 좌표를 그대로 각도 공식에 넣으면
각도가 왜곡된다(실측: 720x900 사진에서 약 6도 차이). 좌표만으로는 알 수
없는 값이라 클라이언트가 함께 보내야 한다.

### 응답 (측면)

```json
{
  "success": true,
  "view": "side",
  "near_side": "left",
  "near_side_determined": true,
  "quality": {"is_valid": true, "issue": ""},
  "reliability": {"is_reliable": true, "issues": []},
  "confidence": 0.918,
  "keypoint_confidence": [{"name": "left_ear", "visibility": 1.0, "band": "높음"}],
  "forward_head": {"angle_deg": -13.23, "verdict": "정상", "note": "..."},
  "round_shoulder": {"angle_deg": 85.38, "verdict": "정상", "note": "..."},
  "disclaimer": "이 결과는 의료 진단이 아닌 참고용 정보이며...",
  "comment": {"text": "...", "source": "agent", "turns": 3, "tool_calls": [...]}
}
```

`reliability.is_reliable`이 `false`면 `comment.source`가 `"skipped"`가 되고
재촬영 안내 문구가 나간다 — 믿을 수 없는 숫자에 그럴듯한 자연어 설명을
붙이면 검증 계층 전체가 무의미해지기 때문이다.

---

## 검증 계층

| 계층 | 잡는 것 |
|---|---|
| 품질 게이트 | 필수 관절 미검출 / 저신뢰 |
| 기하학적 타당성 | **마네킹**, 겹친 좌표, 비인체적 비율 (view별 분기) |
| 측면 전용 검증 | 정면 사진을 측면으로 오인, 옆모습 불충분 |
| 근접 측 판정 | 카메라에 가까운 쪽 (z 깊이 기준) |
| 통합 신뢰도 | 위를 종합 |
| LLM 출력 검증 | 숫자, 판정 뒤집기, 진단 표현 |
| 폴백 | 위 모든 실패 |

---

## 프론트엔드 연동

```js
// frontend/src/lib/postureApi.js
export const POSTURE_AI_BASE =
  import.meta.env.VITE_POSTURE_AI_BASE || 'http://localhost:8001'

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
  if (!res.ok) throw new Error(`분석 실패 (${res.status})`)
  return res.json()
}
```

좌표는 팀의 `usePoseLandmarker` 훅을 그대로 재사용하면 된다 — 스쿼트
의존성이 없는 순수 MediaPipe 로딩 훅이고, `detectPose()`가 33개 배열을
그대로 돌려준다.

```js
const { detectPose } = usePoseLandmarker()
const landmarks = await detectPose(imgElement)
const result = await analyzePosture('side', landmarks, img.naturalWidth, img.naturalHeight)
```

---

## 배포 (docker-compose 추가 예시)

```yaml
  posture-ai:
    build:
      context: ./posture-ai
    ports:
      - "8001:8001"
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
    restart: unless-stopped
```

프론트 빌드 시 `VITE_POSTURE_AI_BASE`를 함께 넘겨야 한다.

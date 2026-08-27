# DTW 템플릿 디렉토리

`app/pose/dtw_matching.py`의 `load_templates()`가 읽는 정규화된 정상 궤적 템플릿(JSON)을
보관하는 곳입니다.

## 현재 상태 (2026-08-27 생성)

**템플릿 20개**가 들어있습니다 — `ml_training/build_dtw_templates.py`로 만들었습니다.

- **영상 렙 12개**: 측면 촬영 4개(`우혁_정상.mp4`, `우혁_정상2.mp4`, `주영_정상.mp4`,
  `형준_정상.mp4`) × 렙 3개씩. 무릎각도가 서있는 기준(150도) 아래로 내려갔다가 다시
  올라오는 구간을 렙 1개로 잘랐다(`ai-progress.md` 2026-08-26 프로토타입과 동일 기준).
- **이미지 구간 8개**: `Dataset/train/Good/*.jpg`(1,001장)를 EXIF 기준으로 검증된 8개
  연속촬영 구간(파일명 끝 하이픈이 경계 마커)으로 나눠, 구간별로 하나의 연속 시계열로
  사용.
- **정규화 기준값**은 이 20개 전체(모든 프레임)를 한 번에 합쳐서 계산했고, 모든 템플릿이
  같은 기준값을 공유한다(`dtw_matching.py` 모듈 docstring의 "정규화 기준값 고정" 원칙).

### 뺀 것: 정면 촬영 1개

"정상" 원본 영상 중 `우혁_정상_정면.mp4`는 **템플릿에서 뺐다**. 이 지표들
(`torso_length_ratio`, `shoulder_forward_lean_deg` 등)은 측면 촬영을 전제로 한
공식(발끝-발목의 좌우 오프셋으로 "몸이 향한 방향"을 추정)이라, 정면 카메라에서는 이
가정이 성립하지 않아 값이 왜곡된다. 좌표 추출 자체는 해뒀지만(체크포인트 파일 참고),
최종 템플릿에는 포함하지 않았다.

체크리스트 문서(`wellmade-squat-criteria-checklist.md`)에는 "측면 3+정면 2, 총 5개"라고
적혀 있지만, 실제 `실제/정상/` 폴더의 파일은 **측면 4 + 정면 1**이다(로우바 2개 제외한
"정상" 태그 영상 5개 중). 이 문서가 실제 상태다 — 체크리스트 쪽 서술이 부정확했던
것으로 보인다.

**정면 지표(무릎모임 기반 고관절 과신전 프록시, `knee_valgus_ratio`)는 이번 템플릿에
포함되지 않았다** — 정면 촬영이 1개뿐이라 의미 있는 템플릿을 만들 수 없다. 주영·형준의
정면 촬영이 추가로 확보되면 별도 템플릿 세트로 다뤄야 한다.

## 다시 만드는 방법

```
cd ai/ml_training
python3 build_dtw_templates.py --step videos   # 영상 5개 → 좌표/렙 추출 (체크포인트)
python3 build_dtw_templates.py --step images   # 이미지 1,001장 → 8구간 추출 (체크포인트)
python3 build_dtw_templates.py --step build     # 체크포인트 → 최종 템플릿 JSON
```

mediapipe/opencv가 로컬에 설치돼 있어야 한다(서버 `requirements.txt`에는 없음 — 의도적,
모듈 docstring 참고). 체크포인트(`ml_training/data/dtw_extraction/*.json`)가 이미 있으면
해당 단계는 건너뛴다 — 소스 영상/사진이 바뀌지 않았다면 `--step build`만 다시 돌려도 된다.

## 아직 정하지 않은 것

- "애매한 구간"을 판별하는 방식(정성/정량)이 미정이라, 이 템플릿을 실제로 판정 로직에
  연결하는 것은 아직 보류 상태다(`dtw_matching.nearest_normal_distance()`는 거리값만
  반환하고 임곗값 판단은 하지 않는다).
- 신고 데이터 기반 템플릿 추가(active learning) 워크플로우도 별도 설계 대상.
- 정면 촬영 데이터가 더 모이면 `knee_valgus_ratio` 기반 별도 템플릿 세트를 추가해야 한다.

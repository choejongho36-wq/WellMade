"""
DTW 템플릿 생성용 로컬 오프라인 스크립트 (mediapipe/opencv 필요, 서버에는 배포하지 않음).

배경: claude/wellmade-squat-criteria-checklist-2026-08-27-addendum.md 4번, 그리고
app/pose/dtw_templates/README.md 참고. 서버는 이미 만들어진 템플릿(숫자 배열)만 읽고,
좌표 추출·템플릿 생성은 로컬에서 이 스크립트로 한다("서버는 복잡한 계산을 하는 곳이
아니다" 원칙).

지표 계산 공식은 frontend/src/pages/MlTestPage.jsx의 calculateAngle/getKneeAngle/
getHipAngle/getShoulderForwardLeanDeg/getTorsoLengthRatio를 그대로 Python으로 옮긴
것이다 — 서버 app/pose/angles.py에는 이 시상면(측면) 지표들이 없다(프론트가 계산해서
보내는 구조라 서버에 원본 공식이 없음, AngleFrame 필드 설명 참고). 공식이 프론트와
어긋나면 실서비스 판정과 템플릿 생성 기준이 달라지므로, 이 파일을 프론트 코드와 함께
검토해야 한다.

사용한 실제 소스와 그 이유는 이 스크립트가 아니라 위 두 문서에 있다 — 여기서는 "어떻게
계산하는지"만 다루고, "왜 이 소스를 골랐는지"는 다루지 않는다.

정면 전용 지표(knee_valgus_ratio 등)는 포함하지 않는다 — 실제 확보된 "정상" 소스 중
정면 촬영은 우혁_정상_정면.mp4 1개뿐이라(체크리스트의 "측면 3+정면 2"라는 서술은 실제
파일 목록과 맞지 않음 — 실제로는 측면 4+정면 1), 정면 지표로 의미 있는 템플릿을 만들 수
없다. 정면 신호(고관절 과신전 의심의 현재 프록시)는 정면 데이터가 더 모이면 별도
템플릿 세트로 다뤄야 한다.

실행: python3 build_dtw_templates.py --step videos   (영상 5개 추출, 체크포인트 저장)
      python3 build_dtw_templates.py --step images   (Dataset/train/Good 8구간 추출)
      python3 build_dtw_templates.py --step build     (체크포인트 → 최종 템플릿 JSON)
단계를 나눈 이유: mediapipe 프레임별 추론이 느려(약 40ms/프레임) 영상 5개(총 2,263
프레임)+이미지 1,001장을 한 번에 돌리면 오래 걸린다. 단계마다 중간 결과를
data/dtw_extraction/*.json에 저장해두면, 중간에 끊겨도 처음부터 다시 돌리지 않아도 된다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

SCRIPT_DIR = Path(__file__).parent
AI_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(AI_DIR))

from app.pose.dtw_matching import (  # noqa: E402
    build_template,
    compute_normalization,
    extract_metric_matrix,
    save_template,
)

DATASET_DIR = Path.home() / "mnt" / "Dataset"
VIDEO_DIR = DATASET_DIR / "실제" / "정상"
IMAGE_DIR = DATASET_DIR / "train" / "Good"
CHECKPOINT_DIR = SCRIPT_DIR / "data" / "dtw_extraction"
TEMPLATE_DIR = AI_DIR / "app" / "pose" / "dtw_templates"

# 로우바 촬영본 제외 확정(체크리스트 참고) — "정상" 중 로우바(우혁_로우바*.mp4)만 뺀
# 나머지 5개.
VIDEO_FILES = [
    "우혁_정상_정면.mp4",
    "우혁_정상.mp4",
    "우혁_정상2.mp4",
    "주영_정상.mp4",
    "형준_정상.mp4",
]

# 시상면(측면) 지표만 사용 — 모듈 docstring 참고.
METRIC_FIELDS = ("knee_angle", "hip_angle", "torso_length_ratio", "shoulder_forward_lean_deg")

# frontend/src/pages/MlTestPage.jsx와 동일한 인덱스.
LEFT_SHOULDER, RIGHT_SHOULDER = 11, 12
LEFT_HIP, RIGHT_HIP = 23, 24
LEFT_KNEE, RIGHT_KNEE = 25, 26
LEFT_ANKLE, RIGHT_ANKLE = 27, 28
LEFT_HEEL, RIGHT_HEEL = 29, 30
LEFT_FOOT_INDEX, RIGHT_FOOT_INDEX = 31, 32
LEFT_EAR, RIGHT_EAR = 7, 8

MIN_RELIABLE_FOOT_LENGTH = 0.03
STANDING_KNEE_ANGLE_DEG = 150.0  # 렙 컷 기준(ai-progress.md 2026-08-26 프로토타입과 동일)
MIN_REP_FRAMES = 5  # 이보다 짧으면 노이즈로 보고 렙에서 제외


def calculate_angle(a, b, c):
    ba = np.array([a["x"] - b["x"], a["y"] - b["y"]])
    bc = np.array([c["x"] - b["x"], c["y"] - b["y"]])
    mag_ba, mag_bc = np.linalg.norm(ba), np.linalg.norm(bc)
    if mag_ba == 0 or mag_bc == 0:
        return 0.0
    cos = np.clip(np.dot(ba, bc) / (mag_ba * mag_bc), -1.0, 1.0)
    return float(np.degrees(np.arccos(cos)))


def select_side(lm):
    left = (lm[LEFT_HIP]["visibility"] + lm[LEFT_KNEE]["visibility"] + lm[LEFT_ANKLE]["visibility"]) / 3
    right = (lm[RIGHT_HIP]["visibility"] + lm[RIGHT_KNEE]["visibility"] + lm[RIGHT_ANKLE]["visibility"]) / 3
    return "left" if left >= right else "right"


def get_knee_angle(lm, side):
    hip, knee, ankle = (
        (LEFT_HIP, LEFT_KNEE, LEFT_ANKLE) if side == "left" else (RIGHT_HIP, RIGHT_KNEE, RIGHT_ANKLE)
    )
    return calculate_angle(lm[hip], lm[knee], lm[ankle])


def get_hip_angle(lm, side):
    shoulder, hip, knee = (
        (LEFT_SHOULDER, LEFT_HIP, LEFT_KNEE) if side == "left" else (RIGHT_SHOULDER, RIGHT_HIP, RIGHT_KNEE)
    )
    return calculate_angle(lm[shoulder], lm[hip], lm[knee])


def get_shoulder_forward_lean_deg(lm, side):
    ear, shoulder, hip, ankle, toe = (
        (LEFT_EAR, LEFT_SHOULDER, LEFT_HIP, LEFT_ANKLE, LEFT_FOOT_INDEX)
        if side == "left"
        else (RIGHT_EAR, RIGHT_SHOULDER, RIGHT_HIP, RIGHT_ANKLE, RIGHT_FOOT_INDEX)
    )
    ear, shoulder, hip, ankle, toe = lm[ear], lm[shoulder], lm[hip], lm[ankle], lm[toe]
    foot_length = abs(ankle["x"] - toe["x"])
    if foot_length < MIN_RELIABLE_FOOT_LENGTH:
        return 0.0
    facing = 1 if (toe["x"] - ankle["x"]) >= 0 else -1

    torso_dx = (shoulder["x"] - hip["x"]) * facing
    torso_dy = shoulder["y"] - hip["y"]
    torso_tilt = np.degrees(np.arctan2(torso_dx, -torso_dy))

    neck_dx = (ear["x"] - shoulder["x"]) * facing
    neck_dy = ear["y"] - shoulder["y"]
    neck_tilt = np.degrees(np.arctan2(neck_dx, -neck_dy))
    return float(neck_tilt - torso_tilt)


def get_torso_length_ratio(lm, side):
    shoulder, hip, ankle, toe = (
        (LEFT_SHOULDER, LEFT_HIP, LEFT_ANKLE, LEFT_FOOT_INDEX)
        if side == "left"
        else (RIGHT_SHOULDER, RIGHT_HIP, RIGHT_ANKLE, RIGHT_FOOT_INDEX)
    )
    shoulder, hip, ankle, toe = lm[shoulder], lm[hip], lm[ankle], lm[toe]
    foot_length = abs(ankle["x"] - toe["x"])
    if foot_length < MIN_RELIABLE_FOOT_LENGTH:
        return None
    torso_length = float(np.hypot(shoulder["x"] - hip["x"], shoulder["y"] - hip["y"]))
    return torso_length / foot_length


def landmarks_to_dicts(pose_landmarks):
    return [{"x": p.x, "y": p.y, "visibility": p.visibility} for p in pose_landmarks.landmark]


def frame_metrics(lm, timestamp):
    side = select_side(lm)
    torso = get_torso_length_ratio(lm, side)
    if torso is None:
        return None  # 발이 안 보여 신뢰 불가 — 이 프레임은 버린다(모듈 docstring 참고).
    return {
        "timestamp": timestamp,
        "knee_angle": get_knee_angle(lm, side),
        "hip_angle": get_hip_angle(lm, side),
        "torso_length_ratio": torso,
        "shoulder_forward_lean_deg": get_shoulder_forward_lean_deg(lm, side),
    }


def cut_reps(frames):
    """무릎각도가 STANDING_KNEE_ANGLE_DEG 아래로 내려갔다가 다시 그 이상으로 올라오는
    구간을 렙 1개로 자른다(ai-progress.md 2026-08-26 프로토타입과 동일 기준)."""
    reps = []
    current = []
    standing = True
    for f in frames:
        below = f["knee_angle"] < STANDING_KNEE_ANGLE_DEG
        if standing and below:
            standing = False
            current = [f]
        elif not standing:
            current.append(f)
            if not below:  # 다시 서는 각도로 올라옴 — 렙 종료
                standing = True
                if len(current) >= MIN_REP_FRAMES:
                    reps.append(current)
                current = []
    return reps


def step_videos():
    import mediapipe as mp

    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    mp_pose = mp.solutions.pose

    for name in VIDEO_FILES:
        out_path = CHECKPOINT_DIR / f"video_{name}.json"
        if out_path.exists():
            print(f"skip (already done): {name}")
            continue

        video_path = VIDEO_DIR / name
        cap = cv2.VideoCapture(str(video_path))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        pose = mp_pose.Pose(
            static_image_mode=False, model_complexity=1,
            min_detection_confidence=0.5, min_tracking_confidence=0.5,
        )

        frames = []
        dropped = 0
        idx = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frame = cv2.resize(frame, (480, 854))
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = pose.process(rgb)
            if result.pose_landmarks is not None:
                lm = landmarks_to_dicts(result.pose_landmarks)
                m = frame_metrics(lm, idx / fps)
                if m is not None:
                    frames.append(m)
                else:
                    dropped += 1
            else:
                dropped += 1
            idx += 1
        cap.release()
        pose.close()

        reps = cut_reps(frames)
        out_path.write_text(
            json.dumps({"source": name, "frames": frames, "reps": reps, "dropped": dropped}, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"{name}: {idx}프레임 중 {len(frames)}개 사용({dropped}개 드롭), 렙 {len(reps)}개 -> {out_path.name}")


def step_images():
    import mediapipe as mp

    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    mp_pose = mp.solutions.pose

    import re

    def sort_key(p: Path):
        m = re.match(r"Good \((\d+)\)(-)?\.jpg", p.name)
        if not m:
            return (999999, 0)
        return (int(m.group(1)), 0 if m.group(2) else 1)

    files = sorted(IMAGE_DIR.glob("*.jpg"), key=sort_key)

    # 파일명 끝 하이픈이 세션(사람/장소) 경계 마커 — 체크리스트에서 검증된 8구간 경계.
    segments = []
    current = []
    for f in files:
        current.append(f)
        if f.name.endswith("-.jpg") and len(current) > 1:
            # 새 마커를 만나면 "마커 직전까지"를 이전 구간으로 닫고, 마커부터 새 구간 시작
            segments.append(current[:-1])
            current = [f]
    if current:
        segments.append(current)

    print(f"이미지 {len(files)}장 -> {len(segments)}개 구간으로 분리")

    pose = mp_pose.Pose(
        static_image_mode=True, model_complexity=1, min_detection_confidence=0.5,
    )
    for seg_idx, seg_files in enumerate(segments):
        out_path = CHECKPOINT_DIR / f"image_segment_{seg_idx}.json"
        if out_path.exists():
            print(f"skip (already done): segment {seg_idx}")
            continue

        frames = []
        dropped = 0
        for order, f in enumerate(seg_files):
            img = cv2.imread(str(f))
            if img is None:
                dropped += 1
                continue
            h, w = img.shape[:2]
            scale = 640 / max(h, w)
            img = cv2.resize(img, (int(w * scale), int(h * scale)))
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            result = pose.process(rgb)
            if result.pose_landmarks is None:
                dropped += 1
                continue
            lm = landmarks_to_dicts(result.pose_landmarks)
            m = frame_metrics(lm, float(order))
            if m is not None:
                frames.append(m)
            else:
                dropped += 1

        out_path.write_text(
            json.dumps(
                {"source": f"image_segment_{seg_idx}", "frames": frames, "dropped": dropped, "n_files": len(seg_files)},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        print(f"segment {seg_idx}: {len(seg_files)}장 중 {len(frames)}개 사용({dropped}개 드롭) -> {out_path.name}")
    pose.close()


def step_build():
    """체크포인트(video_*.json, image_segment_*.json)를 모아 정규화 기준값을 한 번만
    계산하고, 렙/구간마다 템플릿을 만들어 app/pose/dtw_templates/에 저장한다."""
    all_sources = []  # (label, source_name, frames)

    for path in sorted(CHECKPOINT_DIR.glob("video_*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if "정면" in data["source"]:
            # 이 스크립트의 지표(torso_length_ratio, shoulder_forward_lean_deg 등)는
            # 측면 촬영을 전제로 한 공식이다(facing_direction을 발끝-발목의 좌우 오프셋으로
            # 추정 — 정면 카메라에서는 이 가정이 성립하지 않아 값이 왜곡된다). 실제
            # "정상" 소스 중 정면은 이 영상 1개뿐이라(체크리스트 "측면 3+정면 2"는 실제
            # 파일과 안 맞음), 템플릿에서는 제외하고 좌표 추출 체크포인트만 남겨둔다.
            print(f"건너뜀(정면 촬영, 측면 공식 부적합): {data['source']}")
            continue
        for rep_idx, rep in enumerate(data["reps"]):
            all_sources.append(("normal", f"{data['source']}_rep{rep_idx}", rep))

    for path in sorted(CHECKPOINT_DIR.glob("image_segment_*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if len(data["frames"]) >= MIN_REP_FRAMES:
            all_sources.append(("normal", data["source"], data["frames"]))

    if not all_sources:
        print("체크포인트가 없습니다 — 먼저 --step videos / --step images를 실행하세요.")
        return

    # 정규화 기준값은 전체를 합쳐 한 번만 계산(dtw_matching 모듈 docstring 원칙).
    all_frames = [f for _, _, frames in all_sources for f in frames]
    combined_matrix = extract_metric_matrix(all_frames, METRIC_FIELDS)
    normalization = compute_normalization(combined_matrix, METRIC_FIELDS)

    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    # 기존 템플릿 JSON은 지우지 않고 덮어쓴다(같은 이름이면 갱신, dtw_templates는 현재
    # 비어 있으므로 이번 실행에서는 전부 신규 생성).
    count = 0
    for label, source, frames in all_sources:
        template = build_template(label, source, frames, normalization, METRIC_FIELDS)
        out = TEMPLATE_DIR / f"{source}.json"
        save_template(template, out)
        count += 1

    print(f"템플릿 {count}개 저장 완료 -> {TEMPLATE_DIR}")
    print(f"정규화 기준값(평균): {normalization.means}")
    print(f"정규화 기준값(표준편차): {normalization.stds}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--step", choices=["videos", "images", "build"], required=True)
    args = parser.parse_args()
    {"videos": step_videos, "images": step_images, "build": step_build}[args.step]()

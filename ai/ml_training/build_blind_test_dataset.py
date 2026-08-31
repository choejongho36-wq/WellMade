"""
6랩 블라인드 테스트용 데이터셋 생성 스크립트 (1회성, 로컬 실행).

claude/wellmade-ai-progress.md(2026-08-25/26)의 "블라인드 테스트(6/6, 100% 정확)"를
프론트에서 버튼 한 번으로 재현 가능하게 만들기 위해, 그때 썼던 것과 같은 조합
(우혁/주영/형준 각 과신전·정상 영상, 총 6개 영상에서 렙 1개씩)의 실제 관절각도
시계열을 뽑아 JSON으로 저장한다.

정상 3개는 이미 ml_training/build_dtw_templates.py --step videos가 체크포인트로
뽑아둔 걸 재사용(다시 mediapipe 안 돌림). 과신전 3개는 여기서 새로 추출한다
(build_dtw_templates.py는 "정상"만 다뤄서 과신전 영상은 추출된 적이 없었음).
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import cv2
import numpy as np

SCRIPT_DIR = Path(__file__).parent
AI_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(AI_DIR))
sys.path.insert(0, str(SCRIPT_DIR))

from build_dtw_templates import (  # noqa: E402
    frame_metrics, cut_reps, CHECKPOINT_DIR,
)

DATASET_DIR = Path.home() / "mnt" / "Dataset"
HYPEREXT_DIR = DATASET_DIR / "실제" / "과신전"

# (사람, 라벨, 파일명)
HYPEREXT_VIDEOS = [
    ("우혁", "우혁_과신전.mp4"),
    ("주영", "주영_과신전.mp4"),
    ("형준", "형준_과신전.mp4"),
]
NORMAL_CHECKPOINTS = [
    ("우혁", "video_우혁_정상.mp4.json"),
    ("주영", "video_주영_정상.mp4.json"),
    ("형준", "video_형준_정상.mp4.json"),
]

OUT_PATH = SCRIPT_DIR / "data" / "blind_test_6reps.json"


def extract_frames_from_video(video_path: Path) -> list[dict]:
    import mediapipe as mp
    mp_pose = mp.solutions.pose
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    pose = mp_pose.Pose(
        static_image_mode=False, model_complexity=1,
        min_detection_confidence=0.5, min_tracking_confidence=0.5,
    )
    frames = []
    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = pose.process(rgb)
        if result.pose_landmarks:
            lm = [{"x": p.x, "y": p.y, "visibility": p.visibility} for p in result.pose_landmarks.landmark]
            m = frame_metrics(lm, idx / fps)
            if m is not None:
                frames.append(m)
        idx += 1
    cap.release()
    pose.close()
    return frames


def first_valid_rep(frames: list[dict]) -> list[dict]:
    reps = cut_reps(frames)
    if not reps:
        raise ValueError("렙을 하나도 못 잘라냈습니다 (STANDING_KNEE_ANGLE_DEG 기준 미달)")
    return reps[0]


def main():
    entries = []

    for person, filename in HYPEREXT_VIDEOS:
        ckpt = CHECKPOINT_DIR / f"video_{filename}.json"
        if ckpt.exists():
            frames = json.loads(ckpt.read_text(encoding="utf-8"))
            print(f"체크포인트 재사용: {filename} ({len(frames)}프레임)")
        else:
            print(f"추출 중(mediapipe): {filename} ...")
            frames = extract_frames_from_video(HYPEREXT_DIR / filename)
            CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
            ckpt.write_text(json.dumps(frames, ensure_ascii=False), encoding="utf-8")
            print(f"  -> {len(frames)}프레임, 체크포인트 저장 완료")
        rep = first_valid_rep(frames)
        entries.append({
            "id": f"{person}_과신전",
            "person": person,
            "true_label": "과신전",
            "source": filename,
            "frames": rep,
        })
        print(f"  렙 선택: {len(rep)}프레임")

    for person, ckpt_name in NORMAL_CHECKPOINTS:
        ckpt = CHECKPOINT_DIR / ckpt_name
        data = json.loads(ckpt.read_text(encoding="utf-8"))
        # build_dtw_templates.py의 step_videos()가 만든 체크포인트는
        # {"source", "frames", "reps", "dropped"} 형태로 렙이 이미 잘려있다 —
        # 우리가 새로 뽑은 과신전 체크포인트(프레임 리스트 그대로)와 형식이 다르다.
        rep = data["reps"][0]
        entries.append({
            "id": f"{person}_정상",
            "person": person,
            "true_label": "정상",
            "source": ckpt_name.replace("video_", "").replace(".json", ""),
            "frames": rep,
        })
        print(f"정상 체크포인트 재사용: {ckpt_name} -> 렙 {len(rep)}프레임")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(entries, ensure_ascii=False, indent=None), encoding="utf-8")
    print(f"\n완료: {len(entries)}개 렙 -> {OUT_PATH} ({OUT_PATH.stat().st_size / 1024:.1f}KB)")


if __name__ == "__main__":
    main()

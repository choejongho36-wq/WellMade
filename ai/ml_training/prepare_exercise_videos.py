"""
국민체력100 운동 영상을 동작별로 묶어두기 (exercise_videos.json).

원본(app/rag/data/videos.json)은 30,090행이지만 대부분 같은 영상의 구간/썸네일 레코드다.
여기서는 다음 두 조건을 모두 만족하는 것만 남긴다.

  1) 난이도(초급/중급/고급) 태그가 있는 것 - 화면에 "초급 · 실내 · 매트"로 보여줄 정보다.
     원본의 다른 값("1~5", "3")은 난이도가 아니라 체력측정 등급이라 사용자에게 못 보여준다.
  2) 우리 운동 데이터와 같은 동작으로 이어지는 것 - app/exercise/movements.py 참고.

매칭 방식을 근육에서 동작으로 바꾼 이유:
처음에는 타겟 근육(pectorals ↔ Pectoralis Major)으로 이었는데, 그러면 "덤벨 런지" 아래에
"Clamshell" 영상이 붙는다. 근육은 같아도 사용자 눈에는 남의 운동이다. 영상이 일부 운동에만
붙더라도 "이 운동 영상"이 맞는 편이 낫다.

실행:

    cd ai
    python -m ml_training.prepare_exercise_videos
"""

import json
from collections import defaultdict
from pathlib import Path

from app.exercise.movements import movements_of_video

AI_ROOT = Path(__file__).resolve().parent.parent
SOURCE_PATH = AI_ROOT / "app" / "rag" / "data" / "videos.json"
OUTPUT_PATH = AI_ROOT / "app" / "exercise" / "data" / "exercise_videos.json"

# 근육/난이도 정보가 붙어 있는 두 묶음만 본다(나머지는 목록/루틴 레코드).
OPERATIONS_WITH_DETAIL = {"TODZ_VDO_TRNG_GUIDE_I", "TODZ_VDO_TRNG_VIDEO_I"}

# 사용자에게 보여줄 수 있는 난이도 값. 원본에는 체력측정 등급("1~5", "3")이 섞여 있다.
KOREAN_LEVELS = {"초급", "중급", "고급"}

# 동작 하나당 남길 영상 수. 추천에는 운동 하나에 1건만 붙으므로 많이 둘 이유가 없다.
MAX_PER_MOVEMENT = 6


def video_of(row: dict) -> dict:
    place = (row.get("trng_plc_nm") or "").strip()
    tool = (row.get("tool_nm") or "").strip()
    return {
        "name": (row.get("trng_nm") or "").strip(),
        "level": (row.get("ftns_lvl_nm") or "").strip(),
        "place": place or None,
        "tool": tool or None,
        "duration_sec": int(row["vdo_len"]) if str(row.get("vdo_len") or "").isdigit() else None,
        "video_url": (row.get("file_url") or "") + (row.get("file_nm") or ""),
        "muscles_ko": (row.get("trng_mscl_zn_nm") or "").strip() or None,
    }


def _sort_key(video: dict) -> tuple:
    """
    같은 동작 안에서의 순서. 초급을 앞에 두고(이 앱 사용자는 대부분 초보), 나머지는 이름과
    URL로 고정한다 - 실행할 때마다 결과가 달라지면 안 된다.
    """
    level_order = {"초급": 0, "중급": 1, "고급": 2}
    return (level_order.get(video["level"], 3), video["name"], video["video_url"])


def build() -> dict:
    rows = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))

    # URL 기준으로 중복 제거 - 같은 영상이 구간별로 여러 행에 걸쳐 들어 있다
    by_url: dict[str, dict] = {}
    for row in rows:
        if row.get("_operation") not in OPERATIONS_WITH_DETAIL:
            continue
        if (row.get("ftns_lvl_nm") or "").strip() not in KOREAN_LEVELS:
            continue
        if not (row.get("file_nm") or "").endswith(".mp4"):
            continue

        video = video_of(row)
        if not video["name"] or not video["video_url"]:
            continue
        current = by_url.get(video["video_url"])
        if current is None or _sort_key(video) < _sort_key(current):
            by_url[video["video_url"]] = video

    # 동작별로 묶는다. 어느 동작에도 안 걸리는 영상은 버린다(붙일 데가 없다).
    by_movement: dict[str, list] = defaultdict(list)
    for video in by_url.values():
        for movement in movements_of_video(video["name"]):
            by_movement[movement].append(video)

    for movement in by_movement:
        by_movement[movement].sort(key=_sort_key)
        by_movement[movement] = by_movement[movement][:MAX_PER_MOVEMENT]

    return {
        "source": "국민체력100 운동 영상 (한국스포츠정책과학원, 공공데이터포털)",
        "license_note": "영상은 원본 URL로 링크만 하고 재배포하지 않는다.",
        "match_note": (
            "운동 이름과 영상 이름을 같은 '동작'으로 이었다(app/exercise/movements.py). "
            "동작이 안 맞으면 영상을 붙이지 않는다 - 근육만 같은 남의 운동 영상을 붙이지 않기 위해서다."
        ),
        "by_movement": dict(sorted(by_movement.items())),
    }


def main() -> None:
    payload = build()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    total = sum(len(v) for v in payload["by_movement"].values())
    print(f"{OUTPUT_PATH.relative_to(AI_ROOT)} 생성 - 동작 {len(payload['by_movement'])}종, 영상 {total}건")
    for movement, videos in payload["by_movement"].items():
        names = ", ".join(v["name"] for v in videos[:3])
        print(f"  {movement:<16} {len(videos):>2}건  {names}")


if __name__ == "__main__":
    main()

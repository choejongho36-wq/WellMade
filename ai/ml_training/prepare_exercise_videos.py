"""
국민체력100 운동 영상을 근육별로 묶어두기 (exercise_videos.json).

원본(app/rag/data/videos.json)은 30,090행이지만 대부분 같은 영상의 구간/썸네일 레코드라
운동명 기준으로는 1,816종뿐이고, 그중 근육 정보(trng_mscl_eng_nm)가 붙어 있는 건
약 900종이다. 그 900종만 근육별로 묶어두면 추천한 운동에 영상 링크를 붙일 수 있다.

매칭 방식 - 운동명이 아니라 근육으로 잇는다:
exercises_ko의 이름은 "3/4 싯업"처럼 영문 운동명을 옮긴 것이고, 국민체력100은
"팔 굽혀 펴기"처럼 우리말 서술형이라 이름끼리는 거의 안 맞는다. 반면 국민체력100은
영문 근육명(Pectoralis Major 등)을 같이 주고 exercises_ko는 target(pectorals)을 주므로,
근육 사전 하나면 둘을 이을 수 있다.

실행:

    cd ai
    python -m ml_training.prepare_exercise_videos
"""

import json
from collections import defaultdict
from pathlib import Path

AI_ROOT = Path(__file__).resolve().parent.parent
SOURCE_PATH = AI_ROOT / "app" / "rag" / "data" / "videos.json"
OUTPUT_PATH = AI_ROOT / "app" / "exercise" / "data" / "exercise_videos.json"

# 근육 정보가 붙어 있는 두 묶음만 쓴다(나머지는 목록/루틴 레코드라 근육 필드가 비어 있다).
OPERATIONS_WITH_MUSCLE = {"TODZ_VDO_TRNG_GUIDE_I", "TODZ_VDO_TRNG_VIDEO_I"}

# exercises_ko.json의 target(19종) -> 국민체력100 영문 근육명.
# cardiovascular system은 근육이 아니라 계통이라 대응되는 값이 없어 뺐다.
TARGET_TO_MUSCLES = {
    "abs": ["Rectus Abdominis", "Transverse Abdominis"],
    "pectorals": ["Pectoralis Major", "Pectoralis Minor"],
    "biceps": ["Biceps Brachii", "Brachialis"],
    "triceps": ["Triceps Brachii"],
    "delts": ["Deltoid", "Anterior Deltoid", "Middle Deltoid", "Posterior Deltoid"],
    "glutes": ["Gluteus Maximus", "Gluteal", "Gluteus Medius", "Gluteus Minimus"],
    "quads": ["Quadriceps Femoris", "Rectus Femoris", "Vastus Medialis", "Vastus Lateralis"],
    "hamstrings": ["Biceps Femoris", "Hamstring", "Semimembranosus", "Semitendinosus"],
    "calves": ["Gastrocnemius", "Soleus", "Triceps Surae"],
    "lats": ["Latissimus Dorsi"],
    "upper back": ["Trapezius", "Rhomboid", "Teres Major", "Teres Minor", "Infraspinatus"],
    "traps": ["Trapezius", "Lower Trapezius"],
    "spine": [
        "Erector Spinae", "Spinalis Thoracis", "Iliocostalis Lumborum",
        "Multifidus", "Quadratus Lumborum",
    ],
    "forearms": [
        "Brachioradialis", "Hand Flexor", "Wrist Extensors",
        "Flexor Carpi Radialis", "Extensor Carpi Radialis",
    ],
    "adductors": ["Adductors", "Adductor longus", "Adductor Brevis", "Gracilis"],
    "abductors": ["Gluteus Medius", "Gluteus Minimus", "Tensor Fasciae Latae"],
    "serratus anterior": ["Serratus Anterior"],
    "levator scapulae": ["Levator Scapula"],
}

# 근육 하나당 남길 영상 수. 추천에는 운동 하나에 1건만 붙이므로 많이 둘 이유가 없고,
# 파일이 커지면 서버 기동 때마다 읽는 비용만 늘어난다.
MAX_PER_TARGET = 8

# 난이도 태그로 쓸 수 있는 값. 원본에는 체력수준 숫자("1~5", "3")가 섞여 있는데
# 그건 난이도가 아니라 측정 등급이라 사용자에게 보여줄 수 없다.
KOREAN_LEVELS = {"초급", "중급", "고급"}


def video_of(row: dict) -> dict:
    level = (row.get("ftns_lvl_nm") or "").strip()
    place = (row.get("trng_plc_nm") or "").strip()
    tool = (row.get("tool_nm") or "").strip()
    return {
        "name": (row.get("trng_nm") or "").strip(),
        "level": level if level in KOREAN_LEVELS else None,
        "place": place or None,
        "tool": tool or None,
        "duration_sec": int(row["vdo_len"]) if str(row.get("vdo_len") or "").isdigit() else None,
        "video_url": (row.get("file_url") or "") + (row.get("file_nm") or ""),
        "muscles_ko": (row.get("trng_mscl_zn_nm") or "").strip() or None,
    }


def _sort_key(video: dict) -> tuple:
    """
    같은 운동명이 여러 행으로 있을 때 무엇을 남길지, 근육별 목록에서 무엇을 앞에 둘지.
    난이도/장소 태그가 있는 쪽을 우선하고(사용자에게 보여줄 정보가 더 많다), 나머지는
    이름 순으로 고정한다 - 실행할 때마다 결과가 달라지면 안 된다.
    """
    return (
        0 if video["level"] else 1,
        0 if video["place"] else 1,
        video["name"],
        video["video_url"],
    )


def build() -> dict:
    rows = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))

    # 1) 근육 정보가 있는 행만 남기고 운동명 기준으로 중복 제거
    best_by_name: dict[str, dict] = {}
    muscles_by_name: dict[str, set] = defaultdict(set)
    for row in rows:
        if row.get("_operation") not in OPERATIONS_WITH_MUSCLE:
            continue
        raw_muscles = (row.get("trng_mscl_eng_nm") or "").strip()
        name = (row.get("trng_nm") or "").strip()
        if not raw_muscles or not name or not (row.get("file_nm") or "").endswith(".mp4"):
            continue

        muscles_by_name[name].update(m.strip() for m in raw_muscles.split(",") if m.strip())
        video = video_of(row)
        current = best_by_name.get(name)
        if current is None or _sort_key(video) < _sort_key(current):
            best_by_name[name] = video

    # 2) target(운동 데이터의 근육 키) 별로 묶는다
    by_target: dict[str, list] = {}
    for target, muscles in TARGET_TO_MUSCLES.items():
        wanted = set(muscles)
        matched = [
            video for name, video in best_by_name.items()
            if wanted & muscles_by_name[name]
        ]
        matched.sort(key=_sort_key)
        by_target[target] = matched[:MAX_PER_TARGET]

    return {
        "source": "국민체력100 운동 영상 (한국스포츠정책과학원, 공공데이터포털)",
        "license_note": "영상은 원본 URL로 링크만 하고 재배포하지 않는다.",
        "match_note": (
            "운동명이 아니라 근육으로 매칭한다 - exercises_ko의 target과 "
            "국민체력100의 trng_mscl_eng_nm을 TARGET_TO_MUSCLES 사전으로 이었다."
        ),
        "by_target": by_target,
    }


def main() -> None:
    payload = build()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    total = sum(len(v) for v in payload["by_target"].values())
    print(f"{OUTPUT_PATH.relative_to(AI_ROOT)} 생성 - {len(payload['by_target'])}개 근육, 영상 {total}건")
    for target, videos in sorted(payload["by_target"].items()):
        levels = ", ".join(sorted({v["level"] for v in videos if v["level"]})) or "-"
        print(f"  {target:<18} {len(videos):>2}건 (난이도 태그: {levels})")


if __name__ == "__main__":
    main()

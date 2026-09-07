"""
운동 추천 후보 큐레이션 만들기 (exercises_core.json).

왜 필요한가:
추천 v1은 exercises_ko.json 1,324건 전부를 후보로 두고 random.sample로 3개를 뽑았다.
그러면 "덤벨 하이트 플라이"처럼 이름도 낯선 변형이 "덤벨 플라이"보다 먼저 나오고, 뽑을
때마다 답이 달라져서 같은 질문에 다른 추천이 나온다(재현도 안 되고 평가도 못 한다).

그래서 부위별로 사람이 고른 기본 동작만 후보로 쓴다. 고르는 일과 태그(난이도/복합운동/
집에서 가능)는 사람이 exercise_core_seed.json에 적고, 이 스크립트는 그걸 원본 데이터와
합쳐(한국어 이름, 설명, 타겟 근육) 서버가 읽을 파일로 만든다.

나머지 1,000여 건은 버리는 게 아니다 - get_exercise_detail(이름으로 설명 찾기)은 계속
전체를 뒤지므로, 사용자가 "케이블 크로스오버는 어떻게 해?"라고 물으면 그대로 답할 수 있다.

실행:

    cd ai
    python -m ml_training.prepare_exercise_core

시드에 적힌 이름이 원본에 없으면 그 목록을 출력하고 실패한다 - 조용히 빠뜨리면 부위별
후보가 소리 없이 줄어들기 때문이다.
"""

import json
import sys
from collections import Counter
from pathlib import Path

AI_ROOT = Path(__file__).resolve().parent.parent
SOURCE_PATH = AI_ROOT / "app" / "rag" / "data" / "exercises_ko.json"
SEED_PATH = Path(__file__).resolve().parent / "exercise_core_seed.json"
OUTPUT_PATH = AI_ROOT / "app" / "exercise" / "data" / "exercises_core.json"

VALID_DIFFICULTY = {"beginner", "intermediate", "advanced"}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def build() -> dict:
    source = load_json(SOURCE_PATH)
    seed = load_json(SEED_PATH)

    # 같은 이름이 두 번 있는 항목이 있다(예: "lever chest press"). id가 작은 쪽으로 고정해
    # 실행할 때마다 결과가 달라지지 않게 한다.
    by_name: dict[str, dict] = {}
    for exercise in sorted(source, key=lambda e: e["id"]):
        by_name.setdefault(exercise["name"].strip().lower(), exercise)

    groups: dict[str, list] = {}
    missing: list[str] = []

    for body_part, entries in seed.items():
        if body_part.startswith("_"):
            continue
        picked = []
        for entry in entries:
            name = entry["name"].strip().lower()
            source_row = by_name.get(name)
            if source_row is None:
                missing.append(f"{body_part}: {entry['name']}")
                continue
            if entry["difficulty"] not in VALID_DIFFICULTY:
                raise ValueError(f"난이도 값이 이상합니다: {entry}")
            if source_row["body_part"] != body_part:
                raise ValueError(
                    f"시드의 부위와 원본이 다릅니다: {entry['name']} "
                    f"(시드 {body_part} / 원본 {source_row['body_part']})"
                )
            picked.append({
                "id": source_row["id"],
                "name": source_row["name"],
                # 시드가 이름을 덧씌웠으면 그걸 쓴다(원본의 "(male)" 표기 등)
                "name_ko": entry.get("name_ko") or source_row.get("name_ko") or source_row["name"],
                "name_ko_source": source_row.get("name_ko") or source_row["name"],
                "body_part": source_row["body_part"],
                "equipment": source_row["equipment"],
                "target": source_row["target"],
                "secondary_muscles": source_row.get("secondary_muscles") or [],
                "instructions_ko": source_row.get("instructions_ko") or "",
                "difficulty": entry["difficulty"],
                "is_compound": bool(entry["is_compound"]),
                "home_friendly": bool(entry["home_friendly"]),
            })
        groups[body_part] = picked

    if missing:
        print("원본(exercises_ko.json)에 없는 이름이 있습니다:", file=sys.stderr)
        for name in missing:
            print("  -", name, file=sys.stderr)
        raise SystemExit(1)

    return {
        "source": "ExerciseDB (exercises_ko.json) 중 사람이 고른 기본 동작",
        "curation_note": (
            "부위별 기본 동작만 남긴 추천 후보. difficulty/is_compound/home_friendly는 "
            "사람이 붙인 태그이고, 나머지 필드는 원본 그대로다. "
            "이름으로 설명을 찾는 get_exercise_detail은 원본 전체를 계속 쓴다."
        ),
        "groups": groups,
    }


def main() -> None:
    payload = build()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    counts = Counter({bp: len(rows) for bp, rows in payload["groups"].items()})
    total = sum(counts.values())
    print(f"{OUTPUT_PATH.relative_to(AI_ROOT)} 생성 - 총 {total}건")
    for body_part, count in counts.most_common():
        print(f"  {body_part:<12} {count}")


if __name__ == "__main__":
    main()

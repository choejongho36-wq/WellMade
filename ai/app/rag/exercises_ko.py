import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

with open(BASE_DIR / "exercises.json", encoding="utf-8") as f:
    exercises = json.load(f)

filtered = [
    {
        "id": ex["id"],
        "name": ex["name"],
        "body_part": ex["body_part"],
        "equipment": ex["equipment"],
        "target": ex["target"],
        "secondary_muscles": ex["secondary_muscles"],
        "instructions_ko": ex["instructions"].get("ko"),
        "instruction_steps_ko": ex["instruction_steps"].get("ko"),
    }
    for ex in exercises
]

with open(BASE_DIR / "exercises_ko.json", "w", encoding="utf-8") as f:
    json.dump(filtered, f, ensure_ascii=False, indent=2)

print(f"{len(filtered)}개 운동 변환 완료")
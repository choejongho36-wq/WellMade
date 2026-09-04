"""
"같은 동작인가"를 판단하는 사전 한 곳.

운동 데이터(ExerciseDB)는 영문 이름("dumbbell goblet squat"), 국민체력100 영상은 우리말
서술형 이름("앉았다 일어서기(공)")이라 문자열끼리는 절대 안 맞는다. 그래서 양쪽 이름에서
"무슨 동작인가"(스쿼트/런지/푸시업…)만 뽑아내 그걸로 잇는다.

왜 근육 매칭을 그만뒀나:
처음에는 타겟 근육(pectorals ↔ Pectoralis Major)으로 이었는데, 그러면 "덤벨 런지" 아래에
"Clamshell" 영상이 붙는다. 근육은 같지만 사용자 눈에는 남의 운동이다. 영상이 3개 중 1개만
붙더라도 "이 운동 영상"이 맞는 편이 "참고 영상" 3개보다 낫다는 판단.

전처리 스크립트(ml_training/prepare_exercise_videos.py)와 추천 로직(recommend.py)이 같은
사전을 쓰도록 여기 한 곳에 둔다 - 양쪽에 복사해두면 조용히 어긋난다.
"""

import re

# canonical -> {"video": 영상 이름에 나오는 표현, "exercise": 운동 영문 이름에 나오는 표현}
#
# 영상 이름은 국민체력100 원본 표기 그대로다(우리말 서술형 + 일부 영문).
# 운동 이름은 ExerciseDB의 영문 name이다.
MOVEMENTS: dict[str, dict[str, list[str]]] = {
    "squat": {
        "video": ["앉았다 일어서기", "Side Walk and Squat"],
        "exercise": ["squat"],
    },
    "lunge": {
        "video": ["한발 뒤로 빼고 앞으로 굽히기", "앞발 의자 올려 굽히기", "뒷발 의자 올려 굽히기"],
        "exercise": ["lunge"],
    },
    "deadlift": {
        "video": ["Deadlift"],
        "exercise": ["deadlift"],
    },
    "glute bridge": {
        "video": ["Glute Bridge", "무릎 굽혀 엉덩이 들어올리기"],
        "exercise": ["glute bridge", "hip lift", "bridge"],
    },
    "step-up": {
        "video": ["박스 오르내리기", "계단 오르기"],
        "exercise": ["step-up"],
    },
    "hip abduction": {
        "video": ["Lying Hip Abduction", "옆으로 누워 다리 들어올리기", "다리 옆으로 들어올리기"],
        "exercise": ["hip abduction"],
    },
    "push-up": {
        # "누워서 뒤로 팔 굽혀 펴기"는 딥스에 가까운 동작이라 뺀다 - 이름이 부분 일치할 뿐이다
        "video": ["팔 굽혀 펴기"],
        "video_exclude": ["뒤로"],
        "exercise": ["push-up", "push up"],
    },
    "dip": {
        "video": ["의자 잡고 팔 뒤로 굽히기", "누워서 뒤로 팔 굽혀 펴기"],
        "exercise": ["dip"],
    },
    "front raise": {
        "video": ["아령 앞으로 들어올리기", "밴드 앞 옆으로 들어올리기"],
        "exercise": ["front raise"],
    },
    "rear raise": {
        "video": ["아령 뒤로 들어올리기", "밴드 어깨 뒤로 들어올리기"],
        "exercise": ["rear delt raise", "reverse fly", "rear fly"],
    },
    "y-raise": {
        "video": ["Y Raise"],
        "exercise": ["y-raise"],
    },
    "crunch": {
        "video": ["윗몸 말아 올리기"],
        "exercise": ["crunch", "sit-up", "curl-up"],
    },
    "leg raise": {
        "video": ["앉아서 다리 펴고 들어올리기", "의자에 앉아 다리 펴서 들어올리기", "엎드려 다리 들어올리기"],
        "exercise": ["leg raise", "leg-hip raise", "leg hip raise"],
    },
    "plank": {
        "video": ["엎드려 팔 대고 버티기", "옆으로 팔 대고 버티기"],
        "exercise": ["plank"],
    },
    "back extension": {
        "video": ["엎드려 상체 들어올리기", "슈퍼맨 자세", "Superman Kick"],
        "exercise": ["hyperextension", "back extension"],
    },
    "calf raise": {
        "video": ["발 뒤꿈치 들어올리기"],
        "exercise": ["calf raise", "standing calves", "toe raise"],
    },
    "high knee": {
        "video": ["연속 무릎 올리기", "한발 무릎 올려차기", "Knee Up"],
        "exercise": ["high knee", "knee up"],
    },
    "jump rope": {
        "video": ["줄넘기"],
        "exercise": ["jump rope"],
    },
    "jumping jack": {
        "video": ["다리 모았다 벌려 뛰기", "Banded Jumping Jack"],
        "exercise": ["jack jump", "star jump"],
    },
    "run": {
        "video": ["제자리 뛰기", "왕복 달리기", "50M 달리기"],
        "exercise": ["run", "bear crawl"],
    },
}


def _contains(text: str, word: str, whole_word: bool) -> bool:
    """
    영문 이름은 단어 경계까지 봐야 한다 - "crunch" 안에 "run"이 들어 있어서, 부분 문자열로만
    보면 "frog crunch"에 달리기 영상이 붙는다(실제로 그렇게 나왔다).
    우리말 영상 이름은 띄어쓰기 규칙이 제각각이라 부분 일치로 두고, 예외는 video_exclude로 뺀다.
    """
    if not whole_word:
        return word in text
    return re.search(rf"(?<![a-z]){re.escape(word)}(?![a-z])", text) is not None


def _match(name: str, key: str) -> list[str]:
    text = (name or "").lower()
    whole_word = key == "exercise"
    matched = []
    for canonical, words in MOVEMENTS.items():
        if not any(_contains(text, word.lower(), whole_word) for word in words[key]):
            continue
        # 부분 일치라 다른 동작 이름 안에 걸리는 경우가 있다("뒤로 팔 굽혀 펴기")
        if key == "video" and any(word.lower() in text for word in words.get("video_exclude", [])):
            continue
        matched.append(canonical)
    return matched


def movements_of_video(video_name: str) -> list[str]:
    """국민체력100 영상 이름에서 동작을 뽑는다. 못 맞추면 빈 목록(그 영상은 안 쓴다)."""
    return _match(video_name, "video")


def movements_of_exercise(exercise_name: str) -> list[str]:
    """ExerciseDB 영문 이름에서 동작을 뽑는다. 못 맞추면 빈 목록(그 운동엔 영상을 안 붙인다)."""
    return _match(exercise_name, "exercise")

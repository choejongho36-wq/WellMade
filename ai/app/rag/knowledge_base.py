"""
RAG 지식베이스 (AI-08/09/14).

요구사항 정의서 "3.RAG파이프라인" 시트의 ① 지식베이스 구성 단계에 해당한다. 원래 시트는
"직접 정리 문서 + 공개자료 참고"라고만 적혀 있어, 팀이 이미 준비해둔 문서 세트가 있는지
먼저 확인하는 게 순서라고 판단해 data.go.kr / AI-Hub / 질병관리청 국가건강정보포털을
직접 찾아봤다(2026-08-18~19). 결과:
- AI-Hub의 피트니스 인접 데이터셋은 전부 TB급 영상/모션 캡처 데이터였고, 텍스트 기반
  "자세 교정 가이드" 형태가 아니었다.
- 질병관리청 자료(예: "무릎관절염, 올바로 운동하기")는 실제로 열어봤는데 증상/진단
  (X-ray, MRI) 위주의 임상 정보였고, "무릎이 안쪽으로 모일 때 이렇게 교정하세요" 같은
  동작 교정 코칭과는 결이 달랐다.
그래서 이 파일은 rules.py가 이미 쓰고 있는 것과 같은 급의 출처(NASM, ACE, Mayo Clinic,
Cleveland Clinic, IJSPT)를 참고해 직접 작성한 문서다. 원문을 그대로 옮기지 않고 일반적으로
알려진 가이드라인을 우리 서비스 상황(스쿼트, MediaPipe 랜드마크 기반 판정)에 맞게 풀어서
다시 썼다.

# 2026-08-24: 사용자 요청에 따라 런지 지원을 서비스에서 완전히 제거했다(스쿼트만 지원).
# 런지 전용 문서였던 "lunge_knee_over_toe"(→ 스쿼트 기준으로 다시 써서 "knee_over_toe"로
# 대체)와 "general_lunge_form"(삭제)을 여기서 함께 정리했다 — 나머지 문서들의 본문에서도
# "런지" 언급을 뺐다.

# 골반 비대칭 문서는 다른 문서들과 톤이 다르다 — "교정법"이 아니라 "전문가 상담 권장"으로만
# 쓰여 있다. 이건 검수 여부와 무관하게 의도적인 설계다: harness.py의 H-02 Human-in-the-loop
# 원칙(AI가 의학적으로 민감한 소견을 절대 확정 진단하지 않음)을 지식베이스 콘텐츠 레벨에서도
# 그대로 지키기 위함이므로, 이 문서를 다시 쓰더라도 이 톤(확정 진단 금지)은 유지해야 한다.
#
# source_date는 원문의 최초 게시일이 아니라 "이 요약을 작성하며 해당 출처의 내용을
# 마지막으로 확인한 시점"이다. 공개 웹페이지들이 게시일을 명시하지 않는 경우가 많아
# 정확한 발행일을 알 수 없었다 — 재순위화(H-05 prefer_latest_document)에서 신뢰할 수
# 있는 "최신성" 신호로 쓰려면, 팀이 원 출처의 실제 개정일을 확인해 교체해야 한다.
"""

from app.pose.coaching_messages import (
    ASYMMETRY_MESSAGE,
    HEEL_LIFT_MESSAGE,
    KNEE_OVER_TOE_MESSAGE,
    KNEE_VALGUS_MESSAGE,
    SHALLOW_SQUAT_MESSAGE,
    SHOULDER_FORWARD_LEAN_MESSAGE,
)

# 이슈 종류(issue_type)/part/ML 라벨명 등 이 프로젝트 여기저기서 쓰이는 여러 표현이
# 같은 문서를 가리킬 수 있어, 검색 매칭을 돕는 태그를 문서마다 여러 개 붙여둔다.
# TF-IDF(char n-gram) 검색은 완전히 다른 단어로는 못 찾으므로(예: "니밸거스" 검색어가
# "무릎 모임" 문서를 못 찾음), 같은 개념의 다른 표현들을 태그로 미리 채워 보완한다.
KNOWLEDGE_BASE = [
    {
        "id": "knee_valgus",
        "title": "스쿼트 무릎 모임(Knee Valgus) 교정",
        "tags": ["knee_valgus", "무릎 모임", "니밸거스", "무릎 안쪽", "knee", "무릎이 안쪽으로"],
        # 규칙기반 판정(app/pose/rules.py)이 쓰는 것과 같은 문구를 재사용한다 —
        # 같은 이슈에 대해 모듈마다 표현이 미묘하게 달라지는 걸 막기 위함(단일 출처 원칙,
        # app/pose/coaching_messages.py 참고).
        "short_message": KNEE_VALGUS_MESSAGE,
        "body": (
            "무릎 모임(knee valgus)은 스쿼트에서 무릎이 발끝보다 안쪽으로 밀려 들어가는 "
            "현상을 말한다. NASM 등 트레이너 자격 기준 자료들은 이를 대개 엉덩이 바깥쪽 근육"
            "(중둔근 등)의 힘이 상대적으로 약하거나, 무릎을 굽히는 동안 발이 안쪽으로 회전하는 "
            "습관 때문에 나타난다고 설명한다.\n\n"
            "교정 방향은 크게 두 가지다. 첫째, 동작 중에는 무릎이 항상 두 번째 발가락 방향을 "
            "향하도록 의식적으로 바깥으로 밀어내는 큐(cue)를 준다. 둘째, 준비 운동으로 밴드를 "
            "무릎 위에 걸고 옆으로 걷는 동작(밴드 워크)이나 클램쉘(조개껍질) 동작처럼 엉덩이 "
            "바깥쪽 근육을 활성화하는 보조 운동을 추천하는 경우가 많다.\n\n"
            "다만 이 현상이 아주 가끔 한두 번 보이는 것과, 반복적으로 계속 나타나는 것은 "
            "구분해서 봐야 한다. 반복적으로 나타난다면 단순히 주의력 문제가 아니라 특정 근육의 "
            "약화나 좌우 불균형이 원인일 수 있으므로, 통증이 동반되면 트레이너나 물리치료사 "
            "상담을 권장한다."
        ),
        "source": "NASM (National Academy of Sports Medicine)",
        "source_url": "https://blog.nasm.org/training-benefits/lunge-effective-lower-body-training-exercise",
        "source_date": "2026-08",
    },
    {
        "id": "squat_shallow",
        "title": "얕은 스쿼트(깊이 부족) 교정",
        "tags": ["squat_shallow", "얕은 스쿼트", "깊이 부족", "shallow", "knee"],
        "short_message": SHALLOW_SQUAT_MESSAGE,
        "body": (
            "스쿼트 깊이가 목표(허벅지가 바닥과 평행해지는 지점)에 못 미치는 경우다. IJSPT의 "
            "스쿼트 생체역학 리뷰 논문은 깊이를 얕음/평행/깊음 세 구간으로 나누는데, 깊이가 "
            "얕을수록 대둔근·햄스트링 등 엉덩이 근육의 참여가 줄고 상대적으로 대퇴사두근에 "
            "부담이 집중되는 경향이 있다고 설명한다.\n\n"
            "깊이가 부족한 흔한 원인은 발목이나 고관절의 가동범위 제한이다. 발뒤꿈치가 쉽게 "
            "뜬다면 발목 가동범위 문제일 가능성이 있고, 무릎보다 허리가 먼저 말리며 더 내려가지 "
            "못한다면 고관절 가동범위 문제일 가능성이 있다. 억지로 더 깊이 앉으려 하기보다는, "
            "먼저 발뒤꿈치를 얇은 판(꿈치 리프트)으로 살짝 들어 발목 부담을 줄여보거나, 준비 "
            "운동으로 고관절을 풀어주는 스트레칭(예: 90/90 스트레칭)을 먼저 시도해보는 것을 "
            "권장한다."
        ),
        "source": "IJSPT (International Journal of Sports Physical Therapy)",
        "source_url": "https://ijspt.scholasticahq.com/article/94600-a-biomechanical-review-of-the-squat-exercise-implications-for-clinical-practice",
        "source_date": "2026-08",
    },
    {
        "id": "heel_rise",
        "title": "발뒤꿈치 뜸(체중 이동) 교정",
        "tags": ["heel_rise", "발뒤꿈치 뜸", "발뒤꿈치", "체중 앞쏠림", "ankle"],
        "short_message": HEEL_LIFT_MESSAGE,
        "body": (
            "스쿼트 중 발뒤꿈치가 바닥에서 떨어지는 현상은 체중이 발 앞쪽으로 쏠렸다는 신호로, "
            "흔히 발목 배측굴곡(발목을 몸 쪽으로 꺾는 동작) 가동범위 제한과 관련이 있다고 "
            "설명된다. 체중이 앞으로 쏠린 채 반복하면 무릎에 걸리는 부담이 커질 수 있다.\n\n"
            "즉각적인 교정 큐로는 '체중을 발뒤꿈치와 발 중앙에 고르게 싣는다'는 감각을 "
            "의식하도록 안내하는 것이 일반적이다. 근본 원인이 발목 가동범위라면, 무릎을 벽 "
            "쪽으로 미는 발목 스트레칭(ankle dorsiflexion stretch)을 준비 운동에 포함하거나, "
            "필요하다면 얇은 굽(꿈치 리프트, 웨지)을 임시로 활용해 발목 부담을 줄여주는 방법도 "
            "함께 안내되곤 한다."
        ),
        "source": "ACE (American Council on Exercise)",
        "source_url": "https://www.acefitness.org/",
        "source_date": "2026-08",
    },
    {
        "id": "squat_asymmetry",
        "title": "스쿼트 좌우 비대칭(체중 쏠림) 교정",
        "tags": ["squat_asymmetry", "좌우 비대칭", "비대칭", "체중 쏠림", "movement"],
        "short_message": ASYMMETRY_MESSAGE,
        "body": (
            "좌우 다리에 실리는 체중이 눈에 띄게 다른 경우다. 한쪽으로 체중이 쏠린 채 반복하면 "
            "쏠리는 쪽 무릎·고관절에 부담이 누적될 수 있다는 점이 일반적으로 지적된다.\n\n"
            "일시적인 쏠림은 카메라 각도나 순간적인 균형 문제일 수 있지만, 반복적으로 같은 "
            "방향으로 쏠린다면 좌우 근력 차이나 과거 부상 이력과 관련이 있을 수 있다. 이 경우 "
            "거울이나 영상으로 스스로 확인하며 '양쪽에 동일한 무게가 실린다'는 느낌을 의식적으로 "
            "맞추는 연습이 1차적으로 권장되며, 반복 패턴이 뚜렷하다면 트레이너나 물리치료사와 "
            "상담해 원인을 확인하는 것이 좋다."
        ),
        "source": "ACE (American Council on Exercise)",
        "source_url": "https://www.acefitness.org/",
        "source_date": "2026-08",
    },
    {
        "id": "shoulder_rounding",
        "title": "어깨 말림(라운드 숄더) 교정",
        "tags": ["shoulder_rounding", "어깨 말림", "라운드 숄더", "shoulder", "굽은 어깨"],
        # 2026-08-24: rules.py/realtime.py의 판정 로직이 shoulder_forward_lean_deg로
        # 바뀌면서(목 기울기 - 상체 기울기 방식), 원인을 어깨로 단정하지 않는 문구로
        # coaching_messages.py에서 갱신됐다 — single source of truth 원칙에 따라 여기도
        # 하드코딩 대신 그 상수를 그대로 가져다 쓴다.
        "short_message": SHOULDER_FORWARD_LEAN_MESSAGE,
        "body": (
            "스쿼트 중 어깨가 앞으로 말리는 것은 흉추(등 윗부분)가 과도하게 굽거나, "
            "가슴 근육이 상대적으로 긴장돼 어깨가 앞으로 당겨지기 때문인 경우가 많다고 "
            "설명된다. NASM의 오버헤드 스쿼트 평가 항목에서도 '가슴을 펴고 흉추를 살짝 편 "
            "상태 유지'를 정상 자세의 기준 중 하나로 본다.\n\n"
            "교정 큐로는 '가슴을 펴고 어깨뼈를 뒤/아래로 가볍게 모은다'는 감각을 의식하도록 "
            "안내하는 것이 일반적이다. 준비 운동으로 가슴 스트레칭(도어웨이 스트레치 등)이나 "
            "등 상부를 강화하는 보조 운동(밴드 로우 등)을 함께 안내하는 경우가 많다."
        ),
        "source": "NASM (National Academy of Sports Medicine)",
        "source_url": "https://blog.nasm.org/newletter/squat-form",
        "source_date": "2026-08",
    },
    {
        "id": "forward_lean",
        "title": "상체 과도한 숙임(Forward Lean) 교정",
        "tags": ["forward_lean", "상체 숙임", "상체 과도", "숙임", "hip"],
        "short_message": "상체가 앞으로 많이 숙여지고 있어요. 가슴을 세우고 엉덩이를 뒤로 빼는 느낌으로 앉아주세요.",
        "body": (
            "스쿼트 중 상체가 과도하게 앞으로 숙여지는 것은 대개 고관절(엉덩이) 가동범위가 "
            "부족하거나, 코어(몸통) 근력이 상대적으로 약해 무게중심을 유지하기 어려울 때 "
            "나타난다고 설명된다. IJSPT의 스쿼트 리뷰 논문은 개인마다 고관절 가동범위 차이가 "
            "커서, '상체를 얼마나 세워야 하는가'에 고정된 정답은 없고 각자의 가동범위 안에서 "
            "척추 중립만 지키면 된다고 강조한다.\n\n"
            "그래서 교정의 핵심은 '무조건 상체를 꼿꼿이 세우라'가 아니라 '척추가 둥글게 말리지 "
            "않는 선에서, 엉덩이를 뒤로 빼며 앉는다'는 감각이다. 만약 이 조정만으로 잘 안 되고 "
            "허리가 계속 말린다면, 발 너비를 조금 넓히거나 무게중심을 살짝 조정해보는 것도 "
            "도움이 될 수 있다."
        ),
        "source": "IJSPT (International Journal of Sports Physical Therapy)",
        "source_url": "https://ijspt.scholasticahq.com/article/94600-a-biomechanical-review-of-the-squat-exercise-implications-for-clinical-practice",
        "source_date": "2026-08",
    },
    {
        # 2026-08-24: 원래 "lunge_knee_over_toe"(런지 전용)였는데, 런지 지원 자체가
        # 제거되면서 스쿼트 기준 문서로 다시 썼다. short_message도 이 이슈에 실제로 쓰이는
        # KNEE_OVER_TOE_MESSAGE로 맞췄다 — 기존에는 LUNGE_FORM_MESSAGE(다른 문구)를 썼는데,
        # get_knee_over_toe_ratio() 판정이 실제로 반환하는 문구와 달라 단일 출처 원칙에
        # 어긋나 있었다.
        "id": "knee_over_toe",
        "title": "무릎이 발끝을 넘는 경우 교정",
        "tags": ["knee_over_toe", "무릎 발끝", "knee"],
        "short_message": KNEE_OVER_TOE_MESSAGE,
        "body": (
            "스쿼트에서 무릎이 발끝을 많이 넘어가면 무릎 관절(특히 슬개골 아래쪽)에 걸리는 "
            "부담이 커질 수 있다고 설명된다. NASM의 오버헤드 스쿼트 평가에서도 무릎이 발끝을 "
            "과도하게 넘지 않는 것을 정상 자세의 기준 중 하나로 본다.\n\n"
            "교정 방향은 '무릎이 발끝을 넘지 않는 선에서 허벅지가 바닥과 평행해지는 지점까지만 "
            "앉는다'는 감각으로 동작을 조절하는 것이다. 발목 가동범위가 부족하면 무릎이 쉽게 "
            "발끝을 넘어가므로, 준비 운동으로 발목 스트레칭을 함께 해보는 것도 도움이 될 수 "
            "있다."
        ),
        "source": "NASM (National Academy of Sports Medicine)",
        "source_url": "https://blog.nasm.org/newletter/squat-form",
        "source_date": "2026-08",
    },
    {
        "id": "movement_jitter",
        "title": "동작이 불안정하게 흔들릴 때(속도 조절)",
        "tags": ["movement_jitter", "불안정", "흔들림", "movement", "속도"],
        "short_message": "움직임이 불안정합니다. 천천히, 일정한 속도로 동작해 주세요.",
        "body": (
            "동작 중 관절 각도가 크게 요동친다면, 근력이 아직 동작을 완전히 통제할 만큼 "
            "충분하지 않거나(특히 처음 시작하는 사람), 너무 빠른 속도로 반복하고 있어 "
            "관성에 의존해 움직이고 있을 가능성이 있다고 일반적으로 설명된다.\n\n"
            "가장 먼저 시도할 수 있는 교정은 반복 속도를 늦추는 것이다. 내려가는 동작(3~4초)과 "
            "올라오는 동작(2~3초)에 각각 목표 시간을 두고 천천히 통제하며 움직이면, 관절 각도의 "
            "변화가 훨씬 매끄러워지는 경우가 많다. 속도를 늦춰도 흔들림이 계속된다면 무게(또는 "
            "난이도)를 낮추고 기본 동작 패턴부터 다시 다지는 것을 권장한다."
        ),
        "source": "ACE (American Council on Exercise)",
        "source_url": "https://www.acefitness.org/",
        "source_date": "2026-08",
    },
    {
        "id": "pelvis_asymmetry",
        "title": "골반 좌우 높이차(비대칭) 관련 안내",
        "tags": ["pelvis_asymmetry", "골반 비대칭", "골반", "hip", "pelvis"],
        # H-02 원칙(하네스가 절대 확정 진단을 내리지 않음)과 동일하게, 이 문서의 short_message도
        # "교정법"이 아니라 "전문가 상담을 권장"하는 톤으로만 작성한다. 다른 문서들과 달리
        # 스스로 고치라는 지시를 주지 않는다는 점이 이 문서의 핵심 설계 의도다.
        "short_message": "골반 좌우 높이차가 반복적으로 감지되고 있어요. 정확한 원인 확인을 위해 전문가(의사·물리치료사) 상담을 받아보시는 걸 권장드려요.",
        "body": (
            "골반 좌우 높이차(골반 기울기)는 다리 길이 차이, 좌우 근력 불균형, 자세 습관 등 "
            "여러 원인으로 나타날 수 있다고 알려져 있다. 카메라 각도나 촬영 순간의 자세만으로도 "
            "일시적인 오차가 생길 수 있어, 한두 번의 측정만으로 실제 신체 비대칭이라고 "
            "단정하기는 어렵다.\n\n"
            "Mayo Clinic, Cleveland Clinic 등 의료 정보 자료들은 공통적으로 골반 비대칭이 "
            "반복적으로 확인되거나 통증을 동반한다면, 자가 진단이나 운동 앱의 안내만으로 "
            "판단하지 말고 의사나 물리치료사 등 전문가의 정밀한 평가를 받을 것을 권장한다. "
            "이 서비스도 같은 원칙을 따른다 — AI는 '반복적으로 감지되고 있다'는 관찰 결과만 "
            "안내하고, 원인이 무엇인지나 어떻게 고쳐야 하는지는 확정해서 알려주지 않는다."
        ),
        "source": "Mayo Clinic / Cleveland Clinic",
        "source_url": "https://www.mayoclinic.org/",
        "source_date": "2026-08",
    },
    {
        "id": "general_squat_form",
        "title": "스쿼트 기본 자세 가이드",
        "tags": ["squat", "스쿼트", "기본 자세", "general"],
        "short_message": "발은 어깨너비로 벌리고, 무릎이 발끝 방향을 향하도록 유지하며 허벅지가 바닥과 평행해질 때까지 앉아주세요.",
        "body": (
            "스쿼트의 기본 자세는 발을 어깨너비 정도로 벌리고 서서, 엉덩이를 뒤로 빼며 무릎을 "
            "굽혀 앉는 동작이다. NASM·ACE 등 트레이너 자격 기준 자료들이 공통으로 강조하는 "
            "핵심 포인트는 세 가지로 정리된다: (1) 무릎이 발끝과 같은 방향을 유지할 것(안쪽으로 "
            "모이지 않게), (2) 척추가 중립을 유지할 것(과도하게 말리거나 젖혀지지 않게), "
            "(3) 체중이 발 전체(특히 발뒤꿈치)에 고르게 실릴 것.\n\n"
            "목표 깊이는 대개 '허벅지가 바닥과 평행해지는 지점'을 기준으로 삼는다. 이보다 더 "
            "깊게 앉는 것(딥 스쿼트)이 반드시 더 좋은 것은 아니며, 개인의 발목·고관절 가동범위에 "
            "따라 적정 깊이가 달라질 수 있다."
        ),
        "source": "NASM / ACE",
        "source_url": "https://blog.nasm.org/newletter/squat-form",
        "source_date": "2026-08",
    },
    {
        "id": "warmup_cooldown",
        "title": "준비운동·마무리 스트레칭 일반 가이드",
        "tags": ["warmup", "cooldown", "준비운동", "스트레칭", "마무리"],
        "short_message": "운동 전에는 가볍게 몸을 풀어주는 동적 스트레칭을, 운동 후에는 사용한 근육을 천천히 늘려주는 정적 스트레칭을 해주세요.",
        "body": (
            "일반적으로 운동 전에는 관절을 움직이며 체온을 올리는 동적 스트레칭(예: 다리 "
            "스윙, 몸통 회전)이, 운동 후에는 한 자세를 20~30초 정도 유지하며 근육을 늘리는 "
            "정적 스트레칭이 권장된다고 알려져 있다. 스쿼트처럼 하체 위주의 운동이라면 "
            "고관절 굴곡근, 햄스트링, 종아리(비복근)를 중심으로 마무리 스트레칭을 하는 것이 "
            "흔히 권장된다.\n\n"
            "한국산업안전보건공단(KOSHA)이 배포한 직업병 예방 스트레칭 자료도 같은 맥락에서, "
            "무리하게 통증이 느껴질 때까지 늘리지 말고 '가볍게 당기는 느낌'까지만 유지할 것을 "
            "강조한다. 통증이 느껴진다면 즉시 멈추는 것이 안전하다."
        ),
        "source": "KOSHA (한국산업안전보건공단)",
        "source_url": "https://www.kosha.or.kr/",
        "source_date": "2026-08",
    },
]


def get_all_documents() -> list[dict]:
    """지식베이스 전체 문서를 반환한다. chunking.py가 이 함수를 호출해 청크로 쪼갠다."""
    return KNOWLEDGE_BASE

"""
서울올림픽기념국민체육진흥공단_국민체력100 동영상 정보 API 수집 스크립트

사용법:
    1. 아래 SERVICE_KEY 에 발급받은 '일반 인증키(Decoding)' 값을 넣으세요.
       (마이페이지에 나온 키는 URL-Encoding된 형태입니다. requests 라이브러리는
        params 로 넘기면 자체적으로 인코딩을 하기 때문에, 이미 인코딩된 키를 그대로
        쓰면 '이중 인코딩'이 되어 401 인증 오류가 납니다. 반드시 '디코딩' 키를 쓰세요.
        마이페이지 > 개발계정 상세에서 '일반 인증키(Decoding)'를 복사하면 됩니다.)
    2. OPERATIONS 리스트에 Swagger 탭에서 확인한 나머지 오퍼레이션 ID를 추가하세요.
       (지금은 확인된 1개만 들어있습니다: TODZ_VDO_TRNG_GUIDE_I - 운동처방가이드)
    3. python fetch_gukmin_cheryeok100_video.py 실행
    4. 결과가 output/videos.json, output/videos.csv 로 저장됩니다.
       이 파일을 챗봇 개발자에게 전달하면 됩니다.
"""

import requests
import json
import csv
import time
import os

# ── 설정 ──────────────────────────────────────────────
SERVICE_KEY = "ge7Kx0uaJmn12ukjG5d8BrMMJlj4tKqNmnsHCMe98ZxufQ/YP16dnzBWThU5ynbygmzB9BSuiy0WeDmwbVZEjw=="
BASE_URL = "https://apis.data.go.kr/B551014/SRVC_TODZ_VDO_PKG"
NUM_OF_ROWS = 100  # 한 번에 가져올 개수 (API 최대치 확인 필요, 보통 100~1000)

# Swagger 탭에서 확인한 전체 7개 오퍼레이션
OPERATIONS = [
    "TODZ_VDO_TRNG_GUIDE_I",     # 운동처방가이드: 연령대별·체력요인별·체력수준별
    "TODZ_VDO_FTNS_CERT_I",      # 체력인증측정방법: 연령대별·체력요인별
    "TODZ_VDO_TRNG_VIDEO_I",     # 운동처방동영상: 연령대별·운동장소별
    "TODZ_VDO_MSCL_TRNG_I",      # 근골격계운동: 연령대별·운동부위별·운동단계별
    "TODZ_VDO_STD_FTNS_I",       # 생애주기별표준운동: 연령대별·운동주차별·운동순서별
    "TODZ_VDO_ROUTINE_I",        # 목적별루틴운동: 연령대별·운동목적별·운동구분별
    "TODZ_VDO_VIEW_ALL_LIST_I",  # 동영상 목록 조회(전체): 운동별·연령대별·소도구및기구별
]
# ─────────────────────────────────────────────────────


def fetch_operation(operation: str) -> list[dict]:
    """한 오퍼레이션의 전체 페이지를 수집해서 리스트로 반환 (타임아웃/연결오류 시 자동 재시도)"""
    all_items = []
    page_no = 1
    MAX_RETRIES = 5

    while True:
        params = {
            "serviceKey": SERVICE_KEY,
            "pageNo": page_no,
            "numOfRows": NUM_OF_ROWS,
            "resultType": "json",
        }
        url = f"{BASE_URL}/{operation}"

        resp = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = requests.get(url, params=params, timeout=20)
                break
            except (requests.exceptions.ConnectTimeout,
                    requests.exceptions.ReadTimeout,
                    requests.exceptions.ConnectionError) as e:
                wait = attempt * 3
                print(f"  [!] {operation} page {page_no}: 연결 오류 ({type(e).__name__}), "
                      f"{wait}초 후 재시도 ({attempt}/{MAX_RETRIES})")
                time.sleep(wait)
        else:
            print(f"  [!] {operation} page {page_no}: {MAX_RETRIES}번 재시도 모두 실패, 이 오퍼레이션 중단")
            break

        if resp.status_code != 200:
            print(f"  [!] {operation} page {page_no}: HTTP {resp.status_code}")
            print(f"      {resp.text[:300]}")
            break

        try:
            data = resp.json()
        except ValueError:
            print(f"  [!] {operation} page {page_no}: JSON 파싱 실패, 응답 앞부분:")
            print(f"      {resp.text[:300]}")
            break

        # data.go.kr 표준 응답 구조: response.body.items
        body = data.get("response", {}).get("body", {})
        items = body.get("items", [])

        # items가 dict 하나로 오는 경우도 있어 리스트로 통일
        if isinstance(items, dict):
            items = items.get("item", [])
        if isinstance(items, dict):
            items = [items]

        if not items:
            break

        for item in items:
            item["_operation"] = operation
        all_items.extend(items)

        total_count = int(body.get("totalCount", 0))
        print(f"  {operation} page {page_no}: {len(items)}건 (누적 {len(all_items)}/{total_count})")

        if len(all_items) >= total_count or not items:
            break

        page_no += 1
        time.sleep(0.2)  # 과도한 호출 방지

    return all_items


def build_rag_chunk(item: dict) -> dict:
    """
    원본 API 응답 하나를 챗봇(RAG)에 바로 넣기 좋은 형태로 정제.

    ⚠️ 주의: data.go.kr 응답의 실제 필드명은 오퍼레이션마다 다를 수 있습니다.
    아래 CANDIDATE_KEYS는 흔히 쓰이는 이름들을 후보로 넣어둔 것이니,
    스크립트를 한 번 실행해서 output/videos.json 을 열어보고
    실제 필드명으로 맞춰서 고쳐주세요 (제일 중요한 단계입니다).
    """

    def pick(*candidates, default=""):
        for c in candidates:
            if c in item and item[c] not in (None, ""):
                return str(item[c]).strip()
        return default

    title = pick("title", "vdoTitle", "vdoNm", "cn", "videoTitle", "videoName")
    description = pick("description", "vdoDc", "cnDc", "contents", "vdoContent")
    category = pick("category", "clCd", "clNm", "classification")
    age_group = pick("ageGroup", "ageNm", "targetAge", "ageDivNm")
    body_part = pick("bodyPart", "exePartNm", "musclePart")
    purpose = pick("purpose", "exePurposeNm", "purposeNm")
    place = pick("place", "exePlaceNm", "placeNm")
    video_url = pick("videoUrl", "vdoUrl", "fileUrl", "mediaUrl")
    thumbnail_url = pick("thumbnailUrl", "thumbUrl", "imgUrl")

    # 임베딩/검색용 텍스트: 제목 + 설명 + 메타 태그들을 하나의 문단으로 결합
    tag_line = " / ".join(
        v for v in [category, age_group, body_part, purpose, place] if v
    )
    text_parts = [p for p in [title, description, tag_line] if p]
    text = "\n".join(text_parts)

    return {
        "id": pick("id", "vdoId", "cntntsId", default=None) or f"{item.get('_operation','')}_{hash(text)}",
        "text": text,
        "metadata": {
            "operation": item.get("_operation", ""),
            "title": title,
            "category": category,
            "age_group": age_group,
            "body_part": body_part,
            "purpose": purpose,
            "place": place,
            "video_url": video_url,
            "thumbnail_url": thumbnail_url,
        },
        # 디버깅/필드명 확인용으로 원본도 같이 보관 (필요 없으면 챗봇 개발자에게 넘길 때 제외 가능)
        "_raw": item,
    }


def load_or_fetch_operation(operation: str) -> list[dict]:
    """이미 수집해서 저장해둔 캐시가 있으면 그걸 쓰고, 없으면 새로 수집 후 저장"""
    cache_path = f"output/_cache_{operation}.json"

    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            items = json.load(f)
        print(f"  (캐시에서 불러옴: {len(items)}건, 다시 받으려면 {cache_path} 삭제 후 재실행)")
        return items

    items = fetch_operation(operation)

    # 부분 실패했더라도 받은 만큼은 저장해서 다음 실행 때 이어받을 수 있게 함
    if items:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)

    return items


def main():
    if "여기에" in SERVICE_KEY:
        print("[!] SERVICE_KEY를 설정하세요 (환경변수 DATA_GO_KR_SERVICE_KEY 또는 스크립트 상단)")
        return

    os.makedirs("output", exist_ok=True)
    all_videos = []

    for op in OPERATIONS:
        print(f"\n=== {op} 수집 시작 ===")
        items = load_or_fetch_operation(op)
        all_videos.extend(items)

    print(f"\n총 {len(all_videos)}건 수집 완료")

    # JSON 저장
    with open("output/videos.json", "w", encoding="utf-8") as f:
        json.dump(all_videos, f, ensure_ascii=False, indent=2)

    # CSV 저장 (모든 항목에서 등장하는 컬럼을 합쳐서 헤더 구성)
    if all_videos:
        fieldnames = []
        for v in all_videos:
            for k in v.keys():
                if k not in fieldnames:
                    fieldnames.append(k)

        with open("output/videos.csv", "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_videos)

    # 정제된 RAG용 데이터셋 저장 (챗봇 개발자에게 넘길 최종 파일)
    rag_chunks = [build_rag_chunk(v) for v in all_videos]
    with open("output/videos_for_chatbot.jsonl", "w", encoding="utf-8") as f:
        for chunk in rag_chunks:
            # 원본(_raw)은 크기가 크므로 전달용 파일에는 빼고 저장
            clean_chunk = {k: v for k, v in chunk.items() if k != "_raw"}
            f.write(json.dumps(clean_chunk, ensure_ascii=False) + "\n")

    print("저장 완료:")
    print("  - output/videos.json          (원본 전체 데이터)")
    print("  - output/videos.csv           (원본 전체 데이터, 표 형태)")
    print("  - output/videos_for_chatbot.jsonl (정제된 RAG용 데이터셋 - 이걸 챗봇 개발자에게 전달)")
    print("\n[!] videos_for_chatbot.jsonl 을 열어서 title/description 등이 비어있으면")
    print("    build_rag_chunk() 안의 CANDIDATE_KEYS를 실제 필드명으로 수정하세요.")


if __name__ == "__main__":
    main()
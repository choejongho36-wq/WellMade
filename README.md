# WellMade

건강관리 서비스. `backend`(Spring Boot) + `frontend`(React/Vite) + `ai`(FastAPI) + MySQL.

---

## 다른 PC에서 세팅하기

**git에 안 올라가는 설정 파일 2개만 복사**하면 되고, 나머지는 툴 설치다.
챗봇/자세추정까지 안 볼 거면 Ollama·AI 서버는 건너뛰어도 백엔드+프론트는 돈다.

### 1. 설치할 툴


| JDK | **21** (Temurin 권장) | 백엔드. Gradle는 wrapper(`gradlew`)라 따로 설치 불필요 |
| Docker Desktop | 최신 | 로컬 MySQL 컨테이너 |
| Node.js | **22 LTS** (vite 8 → Node 20.19+ 필요) | 프론트 |
| Python | **3.12** | AI 서버 (선택) |
| Ollama | 최신 | 챗봇 LLM (선택). 설치 후 `ollama pull qwen2.5:7b-instruct` |
| VS Code | - | `.vscode/launch.json`에 `local` 프로필 실행 설정 있음. Java 확장팩 설치 |

> AI 서버의 `dtaidistance`(자세 DTW)는 Windows에서 빌드에 C 컴파일러(MSVC Build Tools)가 필요하다.
> 자세추정 안 볼 거면 `requirements.txt`에서 빼고 설치해도 된다.

### 2. git에 없는 파일 (기존 PC에서 직접 복사 — USB/클라우드)

`.gitignore`로 빠져 있어 `git pull`로는 안 온다. 비밀키가 들어있어서 그렇다.

```
backend/src/main/resources/application.yml
backend/src/main/resources/application-local.yml   ← 로컬 개발용 실제 키(OAuth, JWT, Gemini 등)
```

`application-local.yml`만 있으면 로컬 개발(`local` 프로필)은 그대로 뜬다.
서버 배포용 루트 `.env`, `ai/.env`는 로컬에서는 없어도 된다(AI는 Gemini/Bedrock 키 쓸 때만 필요).

### 3. 실행

```bash
git clone https://github.com/choejongho36-wq/WellMade.git
cd WellMade
# → 여기서 위 2번 파일들을 backend/src/main/resources/ 에 복사

# MySQL (포트 3307)
cd backend && docker compose up -d

# 백엔드 (localhost:8080) — VS Code면 "WellmadeApplication" 실행(local 프로필 자동)
./gradlew bootRun --args='--spring.profiles.active=local'

# 프론트 (localhost:5173)
cd ../frontend && npm install && npm run dev

# AI 서버 (localhost:8000) — 선택
cd ../ai
python -m venv .venv && source .venv/Scripts/activate   # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

프론트는 `VITE_API_BASE`/`VITE_AI_BASE` 없으면 `localhost:8080`/`localhost:8000`으로 붙으므로 로컬은 설정 불필요.

---

## 배포

서버에서 `./deploy/deploy.sh` (git pull → `docker compose -f docker-compose.prod.yml up -d --build`).

# 배포 (단일 EC2 + Docker Compose)

로컬 개발은 `backend/docker-compose.yml`(MySQL만) 그대로. 이 문서는 서버 배포용.

## 0. 인스턴스 (SSM 접속용)

- IAM 역할에 `AmazonSSMManagedInstanceCore` 부착, 아웃바운드 443 허용
- 최신 Amazon Linux 2023 / Ubuntu AMI면 SSM Agent 기본 포함
- 접속: 로컬에 AWS CLI v2 + Session Manager plugin 설치 후
  `aws ssm start-session --target i-xxxxxxxx`

## 1. 서버 준비 (최초 1회)

SSM 세션은 `ssm-user`(무암호 sudo)로 들어온다.

```bash
sudo dnf install -y git docker            # Ubuntu: sudo apt install -y git docker.io
sudo systemctl enable --now docker
sudo mkdir -p /usr/local/lib/docker/cli-plugins
sudo curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$(uname -m)" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
```

## 2. 코드 + 시크릿

```bash
# private 레포면 GitHub Deploy key(읽기 전용) 또는 PAT 필요
git clone https://github.com/choejongho36-wq/WellMade.git
cd WellMade

cp .env.example .env
nano .env            # 실제 값 입력 (아래 표 참고)
chmod 600 .env
```

`.env` 는 `.gitignore` 에 있어 `git pull` 이 덮어쓰지 않는다.

| 항목 | 발급처 |
|---|---|
| `GOOGLE_/KAKAO_/NAVER_*` | 각 소셜 개발자 콘솔. **redirect URI 에 운영 도메인 등록 필수** |
| `JWT_SECRET` | `openssl rand -base64 32` |
| `GEMINI_API_KEY` | Google AI Studio |
| `DATA_GO_KR_HOLIDAY_KEY` | 공공데이터포털 "한국천문연구원_특일 정보" |
| `ANTHROPIC_API_KEY` | Anthropic 콘솔 |
| `OLLAMA_BASE_URL` | 챗봇 LLM GPU 인스턴스 사설 IP |

## 3. 실행

```bash
sudo docker compose -f docker-compose.prod.yml up -d --build
sudo docker compose -f docker-compose.prod.yml ps
sudo docker compose -f docker-compose.prod.yml logs -f backend
```

- 80 포트로 프론트가 뜨고, 같은 nginx가 `/api` → backend, `/ai` → ai 로 프록시
- HTTPS 는 이 앞에 ALB 또는 Caddy/certbot 을 두거나, nginx.conf 에 TLS 블록 추가

## 4. 업데이트

```bash
git pull
sudo docker compose -f docker-compose.prod.yml up -d --build
```

## 주의

- **작은 인스턴스(t3.micro/small)는 `--build` 중 OOM 가능.** 스왑 2GB 잡거나
  GitHub Actions 에서 이미지 빌드 → GHCR push → 서버는 `pull` 만.
- 프론트 `VITE_*` 는 빌드 타임에 번들에 박힘 → 값 바꾸면 `frontend` 재빌드 필요.
- MySQL 데이터는 `mysql_data` 볼륨에 유지. 스키마는 `ddl-auto: update` 가 생성.

# 배포 (서버에서 직접 빌드)

자동 파이프라인 없이, 서버에 접속해 직접 빌드/재기동한다.

## 평소 배포

서버 접속은 SSM Session Manager로 한다 (SSH 포트 안 씀).

```bash
aws ssm start-session --target i-033f1166c97c824aa --region ap-northeast-2
# 콘솔로 붙어도 된다: EC2 -> 인스턴스 선택 -> 연결 -> Session Manager

cd ~/WellMade
./deploy/deploy.sh
```

`deploy.sh` 가 하는 일: `git pull --ff-only` → `docker compose -f docker-compose.prod.yml up -d --build`
→ 안 쓰는 이미지 정리 → 컨테이너 상태 출력.

`application.yml` / `.env` 는 gitignore라 서버 파일이 그대로 유지된다.

## 서버 최초 1회

```bash
cd ~/WellMade
git checkout main            # 배포는 main 기준
chmod +x deploy/deploy.sh
cp .env.example .env && nano .env
```

## 주의

- 이미지 빌드가 실패하면 기존 컨테이너는 그대로 살아 있다 (`up -d --build` 는 빌드 성공 후에만 교체).
- 빌드를 서버에서 하므로 배포 중 CPU/메모리를 많이 쓴다. 트래픽이 적은 시간대에 하는 편이 안전하다.
- Ollama(챗봇 LLM)는 이 compose에 없다. 별도 GPU 인스턴스에 두고 `.env` 의 `OLLAMA_BASE_URL` 로 가리킨다.

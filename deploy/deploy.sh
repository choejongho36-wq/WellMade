#!/usr/bin/env bash
# GitHub Actions가 SSM으로 이 스크립트를 ssm-user 권한으로 실행한다.
# 서버에 최초 1회: git checkout main && chmod +x deploy/deploy.sh
set -euo pipefail

cd "$(dirname "$0")/.."   # ~/WellMade

echo "== git pull =="
git pull --ff-only

echo "== rebuild & restart =="
# application.yml / .env 는 gitignore라 서버 파일 그대로 유지됨
docker compose -f docker-compose.prod.yml up -d --build

echo "== prune =="
docker image prune -f

echo "== status =="
docker compose -f docker-compose.prod.yml ps

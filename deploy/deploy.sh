#!/usr/bin/env bash
# 서버에서 직접 실행하는 배포 스크립트.
#
#   ssh <서버> && cd ~/WellMade && ./deploy/deploy.sh
#
# 최초 1회: git checkout main && chmod +x deploy/deploy.sh
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

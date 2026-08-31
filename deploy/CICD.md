# CI/CD (GitHub Actions → SSM 배포)

`main` push 시: `bootJar` 컴파일 검증 → OIDC로 AWS 역할 assume → SSM으로 서버에서
`deploy/deploy.sh` 실행 (`git pull` + `docker compose up -d --build`).

`application.yml` / `.env` 는 gitignore라 서버 파일이 그대로 유지되므로 파이프라인이 안 건드림.

---

## 1. 서버 최초 1회

```bash
cd ~/WellMade
git checkout main          # 배포는 main 기준
chmod +x deploy/deploy.sh
```

## 2. AWS OIDC 공급자 (계정당 한 번, 이미 있으면 생략)

```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```
(AWS는 이 공급자에 대해 thumbprint를 실제 검증하지 않지만 API가 값을 요구함)

## 3. 배포용 IAM 역할

`trust-policy.json` — 이 repo의 `main` 브랜치 워크플로만 assume 가능:
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "Federated": "arn:aws:iam::<ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com" },
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": { "token.actions.githubusercontent.com:aud": "sts.amazonaws.com" },
      "StringLike": { "token.actions.githubusercontent.com:sub": "repo:choejongho36-wq/WellMade:ref:refs/heads/main" }
    }
  }]
}
```

`permissions.json` — 그 인스턴스에 셸 명령만:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "ssm:SendCommand",
      "Resource": [
        "arn:aws:ssm:ap-northeast-2::document/AWS-RunShellScript",
        "arn:aws:ec2:ap-northeast-2:<ACCOUNT_ID>:instance/i-033f1166c97c824aa"
      ]
    },
    { "Effect": "Allow", "Action": "ssm:GetCommandInvocation", "Resource": "*" }
  ]
}
```

```bash
aws iam create-role --role-name wellmade-github-deploy \
  --assume-role-policy-document file://trust-policy.json
aws iam put-role-policy --role-name wellmade-github-deploy \
  --policy-name ssm-deploy --policy-document file://permissions.json
```

## 4. GitHub Secrets (repo Settings → Secrets and variables → Actions)

| 이름 | 값 |
|---|---|
| `AWS_DEPLOY_ROLE_ARN` | `arn:aws:iam::<ACCOUNT_ID>:role/wellmade-github-deploy` |
| `EC2_INSTANCE_ID` | `i-033f1166c97c824aa` |

## 5. 배포 흐름

- 평소 작업은 `AKI` 등 브랜치에서 → 릴리스할 때 `main`으로 merge → 자동 배포
- 수동 실행: Actions 탭 → deploy → "Run workflow"
- 실패 시 서버의 기존 컨테이너는 그대로 유지됨 (`up -d --build` 가 새 이미지 빌드 실패하면 교체 안 함)

## 나중에 (지금은 생략)

- 이미지를 GHCR에 빌드·푸시하고 서버는 `pull`만 → t3.large 빌드 부하 제거
- CI에서 테스트 실행 (`application.yml` 을 secret으로 생성 + MySQL service container 필요)
- DB 백업 크론, `docker system prune` 주간 크론

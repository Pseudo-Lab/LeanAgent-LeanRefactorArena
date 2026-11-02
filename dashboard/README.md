# 팀 대시보드

기본 화면은 **최종 F001–F060의 원본 length·HB**입니다. 상단에서 웜업 팀 결과로 전환합니다.
기존 문제 타일·상세 패널 양식을 사용합니다. 개선 결과가 없으면 회색이며, 점수가 있으면
60점 이하 빨강, 60점 초과 초록 농도로 표시합니다. 원본 측정값을 개선 점수로 취급하지 않습니다.
타일 하단은 원본 length·raw HB이고, 원본 표본·실행 근거는 상세 패널에서 펼칩니다.
현재 최종 원본 스냅샷은 length·HB 모두 60개를 포함합니다. HB는 3회 중앙값 48개와
1회 잠정값 12개이며, 기존 로컬 배치 37개에 별도 원본 측정 23개를 추가했습니다. 없는 HB는
`null`/미측정으로 표시합니다. 후보 탐색 완료 여부와 원본 측정 여부는 별개입니다.

웜업 P01–P15의 팀원 후보와 공통 환경에서 재검증한 결과를 보여줍니다.
공식 제출 성적이 아니며 자료 미확보·환경 준비 실패·검증기 지원 대기·증명 실패를 구분합니다.
일부 버전만 통과한 후보는 대표 환경의 측정값과 미완료 호환성을 구분해 표시합니다.


후보 출처와 검증 상태는 `../submissions/warmup/manifest.json`에 있습니다.
제출 후보·출처·재검증 실행법은 `../submissions/warmup/README.md`에 있습니다.
문제별 대표 표시는 담당자 최종본을 우선하며, 다른 후보도 상세 화면에서 확인할 수 있습니다.
동일한 15개 대표 후보는 `../submissions/warmup/best/`에 보관하며, 제출 준비 묶음의 `manifest.json`에서 파일 해시와 검증 상태를 확인할 수 있습니다.


## 실행

Node.js 24에서 이 폴더를 열고 실행합니다.

```sh
npm ci
npm run dev
```

주소: http://127.0.0.1:4173

## 데이터

### 최종 원본 기준값

`public/data/final-baselines.json`은 `src/lib/final-baselines.ts`의 별도 계약을 사용합니다.
length는 SHA-256 `d53690b057f9…` 데이터셋의 `proof_length`, 로컬 length·HB는
`20261101-final60-usd1-r1`과 아래 추가 실행의 `problems/Fxxx/baseline/result.json`에서 가져왔습니다.
추가 실행은 `20261102-speed-pilot`, `20261102-remaining22`, `20261102-provisional12`입니다.
HB는 첫 지정 버전에서 측정한 값입니다. `sampleCount: 3`은 raw 표본 3회의 중앙값,
`sampleCount: 1`은 속도를 우선한 잠정값입니다. scaled 값(`raw // 1000`)과 실제 표본도
상세 화면에 표시합니다. 원본 기준값이며 개선 점수나 공식 Linux worker 성적이 아닙니다.
전체 지정 버전 통과 여부나 유료 후보 실행의 비용 정산 완료를 이 화면에서 판정하지 않습니다.

저장소 루트에서 다음 명령으로 기존 기록만 다시 가져옵니다. Lean·모델·네트워크를 실행하지 않으며
원본 실행 폴더를 수정하지 않습니다. 두 입력 경로는 실제 로컬 기록 위치로 지정합니다.

```sh
python3 dashboard/scripts/export_final_baselines.py \
  --dataset /ABSOLUTE/PATH/benchmark_data_final.jsonl \
  --run-root /ABSOLUTE/PATH/20261101-final60-usd1-r1
```

원본 전용 실행기로 추가한 측정은 `--supplement /ABSOLUTE/PATH/BASELINE-RUN`으로 합칩니다.
옵션은 반복할 수 있습니다. 그룹 시작·끝 전체 환경 검증을 통과한 문제만 받아들이며,
각 문제에 실제 실행 ID를 기록합니다. 측정 중인 그룹이나 실패한 문제는 미측정으로 남습니다.

가져오기는 데이터셋 SHA, 문제의 원본·명제·이름, 정상 종료, 저장된 소스·로그 해시,
로그 측정값·실제 표본 수·집계값을 확인합니다. 완료 기록이 없으면 미측정으로 남기고,
있는 기록이 잘못됐으면 내보내기를 중단합니다. 원본 길이를 HB나 0점으로 대체하지 않습니다.
내보낸 파일은 실행 루트 상대 경로와 해시만 포함하며 절대 경로·API 응답·자격 증명은 포함하지 않습니다.
갱신한 JSON을 검토하고 아래 검사·빌드를 거친 뒤 배포하면 반영됩니다. 브라우저 자동 수집은 없습니다.

### 웜업·기존 대회 형식

결과 JSON은 `public/data/`에 두고 `index.json`에 파일 이름을 적습니다.
파일 형식은 `src/lib/model.ts`에 있습니다. `warmup`은 15문제, `competition`은 50문제를 받습니다.
P10·P11·P13·P14·P15의 웜업 JSON은 `scripts/publish_warmup_verification.py`로 검증 artifact에서 갱신하며 점수를 직접 편집하지 않습니다. 나머지 문제는 기존 측정 결과를 유지합니다. 확인하지 않은 결과는 대기로 표시합니다.
JSON 불러오기는 현재 화면에서만 적용됩니다.

## 팀 PR과 개선 조사

`src/data/team-activity.json`은 2026-10-26에 확인한 모든 상태의 팀 PR 30개와 작성자 7명, 주요 실험 36묶음의 출처 목록입니다. 병합 전 결과는 작성자 보고값으로 표시하며, 점수표의 공통 환경 측정과 합산하지 않습니다. 개별 시도 전체는 원문 기록으로 연결합니다. PR #24의 파일 목록 API는 3,000개 제한이 있어 하위 트리와 보고서도 확인했습니다.

P09의 호환성 보완 근거는 `public/research/p09/experiment.json`에 있습니다. 공개된 후보와 정확히 같은 바이트·해시의 증명 및 원본을 지정된 세 버전·커밋·의존성에서 각각 3회 전체 파일 검증했습니다. 이 근거로 P09의 상태와 호환성만 보완했으며, 기존 v4.32 성능 측정값과 스냅샷 측정일은 유지합니다. `submissions/warmup/`은 이전 제출 준비 시점의 기록이며 이번 호환성 보완이나 새 제출을 반영한 묶음이 아닙니다.

새 76토큰 대안과 기존 79토큰 후보의 성능 비교는 별도의 전체 문맥 측정입니다. 해당 HB를 기존 점수표의 계측값과 섞지 않습니다. 원문 논문과 적용 범위는 화면의 P04·P09 연구에서 확인할 수 있습니다.

## 확인

```sh
npm test
npm run data:check
npm run build
```

## 배포

운영 주소: https://lean-arena-dashboard.pages.dev

Cloudflare Pages의 Direct Upload 프로젝트 `lean-arena-dashboard`를 사용합니다. GitHub Actions 저장소 변수 `DASHBOARD_URL`에도 이 주소를 설정합니다.

`.github/workflows/dashboard-ci.yml`이 main의 `dashboard/**` 또는 해당 워크플로 변경을 처리합니다. PR에서는 테스트·데이터 검사·빌드만 실행하며, main에서는 검사 성공 후 **같은 실행에서 검증한 `dist/` artifact**를 Cloudflare Pages로 배포합니다. Actions의 수동 실행도 main에서만 운영 배포합니다. Cloudflare의 별도 Git 연결이나 팀원별 유료 좌석은 필요하지 않습니다.

### 최초 연결

1. Cloudflare **Workers & Pages → Create application → Pages → Direct Upload**에서 프로젝트를 만들고 운영 브랜치를 `main`으로 설정합니다.
2. 대상 계정으로 범위를 제한한 **Account → Cloudflare Pages → Edit** 권한의 API 토큰을 만듭니다.
3. 이 저장소의 **Settings → Secrets and variables → Actions**에 다음 항목을 등록합니다. 토큰은 코드·문서·채팅에 붙이지 않습니다.

| 종류 | 이름 | 값 |
| --- | --- | --- |
| Secret | `CLOUDFLARE_API_TOKEN` | 대상 계정의 Pages 배포 권한을 가진 API 토큰 |
| Variable | `CLOUDFLARE_ACCOUNT_ID` | Cloudflare 계정 ID |
| Variable | `CLOUDFLARE_PAGES_PROJECT` | 생성한 Pages 프로젝트 이름 |
| Variable | `DASHBOARD_URL` | 해당 프로젝트의 실제 운영 URL (`https://…pages.dev`) |

Wrangler CLI는 `4.152.0`으로 고정합니다. 배포 토큰 `lean-arena-github-actions`의 만료일은 2027-10-26이며, 만료 전에 Secret을 갱신합니다. 필수 설정이 없으면 배포 단계가 명시적인 오류로 중단됩니다.

### 배포 확인과 재실행

`public/_headers`의 보안 헤더와 데이터 재검증 캐시 정책은 Vite 빌드 결과에도 포함됩니다. 배포 후 `npm run deploy:check`가 `DASHBOARD_URL`의 데이터 목록 및 모든 스냅샷 JSON을 해당 커밋과 비교합니다. 이전 데이터가 남아 있으면 배포 작업은 실패합니다.

로컬에서 운영 데이터를 확인하려면 다음과 같이 실제 주소를 지정합니다.

```sh
DASHBOARD_URL=https://lean-arena-dashboard.pages.dev npm run deploy:check
```

재배포는 GitHub Actions의 **Dashboard CI and Production → Run workflow → main**에서 실행합니다. `check` 성공만으로 운영 배포가 끝난 것은 아니며, `deploy`의 데이터 확인까지 성공했는지 확인합니다. PR·다른 브랜치에서 수동 실행하면 검증만 수행합니다.

Cloudflare에서 운영 확인을 마친 후 기존 Vercel 자동 배포용 Secret과 변수를 정리할 수 있습니다. 이전 Vercel 프로젝트는 전환 확인 전까지 복구용으로 유지합니다.

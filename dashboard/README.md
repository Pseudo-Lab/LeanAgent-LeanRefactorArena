# 팀 대시보드

Final 화면은 기존 40개 결과와 남성우·손지연님의 공유 후보 40개를 비교해 전체 60문제의 최고 점수를 표시합니다. Strata·LeanPool 20문제의 기존 결과는 유지합니다. PhysLib·CSLib은 정소미·남성우님의 후보를 문제별로 비교하고, ArkLib·PutnamBench는 손지연님의 결과를 연결합니다. 상세 화면의 후보 비교표에서 선택 출처와 다른 후보의 점수를 확인할 수 있습니다.

`public/data/team-shared-results.json`은 `scripts/publish_team_shared_results.py`로 공유 자료에서 생성합니다. 이번 업데이트에서 Lean 측정이나 API 호출을 실행하지 않습니다. 각 출처의 paired 토큰·HB로 대회식 종합 점수를 계산하며, 원자료와 비용 범위는 `../solutions/team-shared-20261102/README.md`에 기록합니다. CI와 배포 검사는 새 공유 결과 JSON도 대조합니다.

기본 화면은 **최종 F001–F060의 원본 기준값과 Strata·PhysLib·CSLib·LeanPool 40문제 검증 풀이**입니다. 상단에서 웜업 팀 결과로 전환합니다.
기존 문제 타일·상세 패널 양식을 사용합니다. 개선 결과가 없으면 회색이며, 점수가 있으면
60점 이하 빨강, 60점 초과 초록 농도로 표시합니다. 원본 측정값을 개선 점수로 취급하지 않습니다.
타일 하단은 원본 length·raw HB이고, 원본 표본·실행 근거는 상세 패널에서 펼칩니다.
현재 최종 원본 스냅샷은 60문제·127개 지정 버전 조합을 모두 포함합니다. 신규 HB는 버전별 1회이며 F001의 기존 3회 표본을 유지합니다. 대표 버전 기준으로 3회 중앙값 1문제·단일 표본 59문제입니다. 이전 대표 버전 3회 기록 48문제·1회 기록 12문제는 `../docs/measurements/final60-primary-history.md`에 보존합니다. 후보 탐색 완료 여부와 원본 측정 여부는 별개입니다.

검증 풀이 F001–F010·F041–F050은 PR #53의 `public/data/final-results.json`과
`../solutions/final20/`에서 가져옵니다. 점수는 해당 후보 실행에서 측정한 원본·후보의
각 3회 HB 표본으로 계산합니다. 다른 실행의 원본 기준값으로 바꾸어 계산하지 않습니다.
검증된 40문제 평균만 표시하고 나머지 20문제와 전체 60문제 평균은 미확보로 남깁니다.
PR #54의 PhysLib·CSLib F011–F030은 `public/data/physlib-cslib-results.json`에 공개 manifest와 JSONL을 대조해 연결합니다. 대표 버전 3회 측정·42개 버전 통과라는 요약을 보존하며, 원시 HB 표본·compiler 로그·실행 fingerprint를 만들어 넣지 않습니다. UI에서 검증 요약과 원시 기록이 있는 후보를 구분합니다. JSONL 선언 SHA와 끝 개행이 하나 더 있는 Lean 파일 SHA를 각각 보존합니다.
재생성: `python3 -B dashboard/scripts/publish_physlib_cslib_results.py` (repo root). `npm run data:check`는 원본 manifest/JSONL/파일/버전/점수를 다시 대조합니다.
상세의 원본 버전별 측정표와 후보 증명·버전 검증은 별도로 표시합니다.
배포 후 검사는 원본 기준값과 후보 결과 JSON 모두를 검증한 소스와 대조합니다.

## 웜업 증명 개선 연구

웜업 P01–P15의 팀원 후보와 공통 환경에서 재검증한 결과를 보여줍니다.
공식 제출 성적이 아니며 자료 미확보·환경 준비 실패·검증기 지원 대기·증명 실패를 구분합니다.
일부 버전만 통과한 후보는 대표 환경의 측정값과 미완료 호환성을 구분해 표시합니다.

정소미가 웜업 P01–P15에서 여러 성능 개선 기법을 시도하고 고정된 원본과 독립적으로 검증한 결과를 보여줍니다. 별도 자료 목록에는 원래 작성자·출처와 팀 활동 기록을 보존합니다. 공식 제출 성적이 아닙니다. 자료 미확보·환경 오류·검증기 지원 범위·증명 실패를 구분하고 미측정을 0점으로 평균내지 않습니다.

대표 후보는 검증된 증명의 원본 대비 토큰·HB 감소율 평균으로 선택합니다. 버전 미완료는 호환성 대기로 남깁니다. 종전 담당자 최종본 우선 선택은 별도 실험 기록에서 볼 수 있으며 모든 원래 후보와 작성자 출처를 보존합니다.

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
`sampleCount: 1`은 실제 단일 계측 표본을 뜻합니다. scaled 값(`raw // 1000`)과 실제 표본도
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
P07·P10·P11·P12·P13·P14·P15의 웜업 JSON은 `scripts/publish_warmup_verification.py`로 검증 artifact에서 갱신하며 점수를 직접 편집하지 않습니다. 이전 실행 [40301978929](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/actions/runs/40301978929)의 7개 summary를 반영했으며, P12 수정 후보도 지정된 세 버전의 Linux 검증을 통과했습니다. P07은 Cslib 지정 버전 3개의 CI 준비를 새로 연결한 상태로, Linux 검증·결과 게시 전까지 대기로 표시합니다. 현재 전체 실행은 10개 환경이며 Cslib 결과도 모두 전달해야 합니다. P07의 대표 측정 버전은 v4.32.0입니다. 평가 대상이 아닌 문제의 측정과 근거 링크는 유지합니다.
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

기본 로컬 주소는 http://127.0.0.1:4173 입니다.

## 웜업 데이터와 근거

- `public/data/warmup-team-results.json`: 현재 대표와 전체 후보, 주 환경 성능, 지정 버전 상태. 형식은 `src/lib/model.ts`에 있습니다.
- `public/data/warmup-team-baseline.json`: 종전 담당자 최종본 우선 선택의 보관 사본.
- `public/research/warmup15/experiment.json`:15문제별 기법·판단·문헌 연결과 실제 작업 경로 변경.
- `public/research/warmup15/p12-v2.json`: P12의 별도 전체 문맥 검증. v4.31.0에서 원본1353/HB9198과 후보886/HB6575를 각각3회 확인했습니다. `separate_verified` 상태로 수치를 표시하되 공통 평균에는 합산하지 않습니다. 동일 후보의 지정 세 버전 확인도 완료했습니다.
- `public/research/warmup15/verification.json`: 원본·출발 후보·새 후보의 측정 counter, 해시와 정확한 버전 근거. 계측 경로가 다른 진단 결과는 점수표에 섞지 않습니다.
- `public/research/external/problem-literature.json`: 기존 63편·종전 추가 4편과 중복되지 않는 새 6편의 원문 방법 대조와 문제별 후속 실험 설계. P05–P12 우선이며, 15문제 전체의 분야 문헌 확보나 새 성능 결과를 뜻하지 않습니다. 인용 구절·PDF 해시는 같은 폴더의 `reading-evidence.json`에 있습니다.
- `public/research/literature.json`: 저장소에서 확인한 arXiv 61편과 ACL 2편 및 추가 조사 문헌. 초록만 확인한 자료와 방법 절까지 확인한 자료를 구분합니다. 방법군의 적용이며 학습·검색 시스템 전체의 재현은 아닙니다.
- `src/data/team-activity.json`:2026-10-26 수집한7명·PR30개·실험36묶음. 작성자 보고값과 공통 재검증값을 분리합니다. PR24의 파일 목록 API 제한도 기록했습니다.
- `public/research/p09/experiment.json`: 동일한79토큰 증명과 원본이 정확한 세 지정 버전에서 각각3회 통과한 근거. 별도 전체 문맥 도구의1HB 미세 차이는 고정PR3에서 재현되지 않았습니다.

`measuredAt`은 혼합 자료의 갱신 시각입니다. 실제 측정일·환경과 보관 결과 재사용 여부는 각 실험 근거를 확인합니다. 후보 작성과 검증 실행에는 Codex 보조를 사용했습니다. 문제별 모델 비용 장부와 예산 제한을 갖춘 대회용 자동 재현 실행은 아직 확인하지 않았습니다.

현재 대시보드 선택과 `../submissions/warmup/best/`, `manifest.json`은 같은 proof SHA-256을 사용합니다. 제출 준비·실행법은 `../submissions/warmup/README.md`에 있습니다. JSON 불러오기는 현재 브라우저 화면에만 적용됩니다.

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

## 지정 버전 전체의 확정 원본 기준값

`final-baselines.json`은 60문제·127개 지정 버전 조합의 완료 결과를 사용합니다. Final 전용 화면과 웜업 전환은 유지하며, 상세 화면에서 버전별 raw HB·환산 HB·실제 표본 수·revision을 확인합니다. 신규 표본은 버전별 1회이고 F001의 기존 3회는 보존합니다. 단일 표본 수와 환경 무결성·컴파일·공리 검증 완료 여부를 구분하며, 원본을 개선 후보 결과로 집계하지 않습니다.

비교 Length는 Final 평가기의 `arena-paper-compatible-v1`과 60문제 모두 일치하는 제공값입니다. 별도 `lean-source-anchored-v1` 감사 값도 보존하며 F053·F056은 1토큰 차이를 표시합니다. 최신 표와 환경 준비 설명은 `../docs/measurements/final60-baselines.md`, `final60-environments.md`에 있습니다.

저장소 루트에서 `python3 -B dashboard/scripts/publish_final_baselines.py`를 실행하면 완료된 측정 문서와 원시 증거를 검증해 기존 공개 파일을 갱신합니다. 60/60 완료·종료 해시 검사·17개 환경과 8개 compiler의 최종 감사가 통과해야 합니다. 다른 실행은 `--run-root`, `--audit`로 지정합니다. 기존 `export_final_baselines.py`는 대표 버전의 과거 기록을 읽는 용도로 유지합니다. 공개 CI는 전체 지정 버전의 완료·identity·Length·HB 표본을 측정 JSON과 환경 lock에 대조합니다.

PR은 검사·빌드만 실행하고, main 병합 시 기존 Cloudflare Pages 운영 배포가 실행됩니다. Final 측정 JSON·환경 lock 변경도 Dashboard CI를 실행합니다.

### 이전 Vercel 배포 기록 (PR #17 시점)

현재 운영 배포는 위 Cloudflare Pages 경로입니다. 아래는 PR #17 작성 당시 Vercel 배포 상태의 기록이며, PR #17이 추가한 `inspect_url` 수동 입력과 `inspect` 작업은 기존 Vercel 배포 조회용으로 남아 있습니다.

당시 운영 주소는 https://lean-arena-dashboard.vercel.app 였습니다. `.github/workflows/dashboard-ci.yml`은 PR에서 테스트·데이터 검사·빌드를 수행하고 main에서 검사 성공 후 기존 Vercel 프로젝트에 배포했습니다. `npm run deploy:check`까지 통과해야 실제 운영 데이터가 해당 커밋과 같다고 확인할 수 있습니다.

2026-10-26의 배포는 Vercel이 커밋 작성자의 프로젝트 배포 권한 부족으로 차단했습니다. [배포 진단 실행](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/actions/runs/40214095577)에 원인이 남아 있습니다. 저장소 Secret의 인증·업로드는 성공했으며 프로젝트 소유자 측에서 작성자의 배포 권한 연결이 필요합니다. 로컬·저장소 반영과 운영 배포 완료를 구분합니다.

- 기존 프로젝트: `lean-arena-dashboard`, `prj_3e8Wjo50Pwb0G1lNq0Vh22iD9OPS`
- 기존 팀: `jwkweons-projects`, `team_NVZHpKfsscaAUAhvimCrDeGP`
- 저장소 Secret: `VERCEL_TOKEN`
- 고정 CLI:65.0.0

권한 연결 후 **Dashboard CI and Production → Run workflow → main**으로 재배포합니다. 기존 배포를 조사할 때 `inspect_url`을 지정하면 조회만 수행하며 운영 배포를 발생시키지 않습니다.

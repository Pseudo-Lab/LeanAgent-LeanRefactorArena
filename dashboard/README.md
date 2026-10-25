# 웜업 증명 개선 연구

정소미가 웜업 P01–P15에서 여러 성능 개선 기법을 시도하고 고정된 원본과 독립적으로 검증한 결과를 보여줍니다. 별도 자료 목록에는 원래 작성자·출처와 팀 활동 기록을 보존합니다. 공식 제출 성적이 아닙니다. 자료 미확보·환경 오류·검증기 지원 범위·증명 실패를 구분하고 미측정을 0점으로 평균내지 않습니다.

대표 후보는 검증된 증명의 원본 대비 토큰·HB 감소율 평균으로 선택합니다. 버전 미완료는 호환성 대기로 남깁니다. 종전 담당자 최종본 우선 선택은 별도 실험 기록에서 볼 수 있으며 모든 원래 후보와 작성자 출처를 보존합니다.

## 실행·확인

Node.js 24에서 이 폴더를 열고 실행합니다.

```sh
npm ci
npm run dev
npm test
npm run data:check
npm run build
```

기본 로컬 주소는 http://127.0.0.1:4173 입니다.

## 데이터와 근거

- `public/data/warmup-team-results.json`: 현재 대표와 전체 후보, 주 환경 성능, 지정 버전 상태. 형식은 `src/lib/model.ts`에 있습니다.
- `public/data/warmup-team-baseline.json`: 종전 담당자 최종본 우선 선택의 보관 사본.
- `public/research/warmup15/experiment.json`:15문제별 기법·판단·문헌 연결과 실제 작업 경로 변경.
- `public/research/warmup15/p12-v2.json`: P12의 별도 전체 문맥 검증. v4.31.0에서 원본1353/HB9198과 후보886/HB6575를 각각3회 확인했습니다. `separate_verified` 상태로 수치를 표시하되 공통 평균에는 합산하지 않습니다. 추가로 v4.29.0 통과를 확인했으며 v4.30.0는 확인 중입니다.
- `public/research/warmup15/verification.json`: 원본·출발 후보·새 후보의 측정 counter, 해시와 정확한 버전 근거. 계측 경로가 다른 진단 결과는 점수표에 섞지 않습니다.
- `public/research/external/problem-literature.json`: 기존 63편·종전 추가 4편과 중복되지 않는 새 6편의 원문 방법 대조와 문제별 후속 실험 설계. P05–P12 우선이며, 15문제 전체의 분야 문헌 확보나 새 성능 결과를 뜻하지 않습니다. 인용 구절·PDF 해시는 같은 폴더의 `reading-evidence.json`에 있습니다.
- `public/research/literature.json`: 저장소에서 확인한 arXiv 61편과 ACL 2편 및 추가 조사 문헌. 초록만 확인한 자료와 방법 절까지 확인한 자료를 구분합니다. 방법군의 적용이며 학습·검색 시스템 전체의 재현은 아닙니다.
- `src/data/team-activity.json`:2026-10-26 수집한7명·PR30개·실험36묶음. 작성자 보고값과 공통 재검증값을 분리합니다. PR24의 파일 목록 API 제한도 기록했습니다.
- `public/research/p09/experiment.json`: 동일한79토큰 증명과 원본이 정확한 세 지정 버전에서 각각3회 통과한 근거. 별도 전체 문맥 도구의1HB 미세 차이는 고정PR3에서 재현되지 않았습니다.

`measuredAt`은 혼합 자료의 갱신 시각입니다. 실제 측정일·환경과 보관 결과 재사용 여부는 각 실험 근거를 확인합니다. 후보 작성과 검증 실행에는 Codex 보조를 사용했습니다. 문제별 모델 비용 장부와 예산 제한을 갖춘 대회용 자동 재현 실행은 아직 확인하지 않았습니다.

현재 대시보드 선택과 `../submissions/warmup/best/`, `manifest.json`은 같은 proof SHA-256을 사용합니다. 제출 준비·실행법은 `../submissions/warmup/README.md`에 있습니다. JSON 불러오기는 현재 브라우저 화면에만 적용됩니다.

## 배포

운영 주소는 https://lean-arena-dashboard.vercel.app 입니다. `.github/workflows/dashboard-ci.yml`은 PR에서 테스트·데이터 검사·빌드를 수행하고 main에서 검사 성공 후 기존 Vercel 프로젝트에 배포합니다. `npm run deploy:check`까지 통과해야 실제 운영 데이터가 해당 커밋과 같다고 확인할 수 있습니다.

2026-10-26의 배포는 Vercel이 커밋 작성자의 프로젝트 배포 권한 부족으로 차단했습니다. [배포 진단 실행](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/actions/runs/40214095577)에 원인이 남아 있습니다. 저장소 Secret의 인증·업로드는 성공했으며 프로젝트 소유자 측에서 작성자의 배포 권한 연결이 필요합니다. 로컬·저장소 반영과 운영 배포 완료를 구분합니다.

- 기존 프로젝트: `lean-arena-dashboard`, `prj_3e8Wjo50Pwb0G1lNq0Vh22iD9OPS`
- 기존 팀: `jwkweons-projects`, `team_NVZHpKfsscaAUAhvimCrDeGP`
- 저장소 Secret: `VERCEL_TOKEN`
- 고정 CLI:65.0.0

권한 연결 후 **Dashboard CI and Production → Run workflow → main**으로 재배포합니다. 기존 배포를 조사할 때 `inspect_url`을 지정하면 조회만 수행하며 운영 배포를 발생시키지 않습니다.

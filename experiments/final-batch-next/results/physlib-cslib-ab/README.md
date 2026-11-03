# physlib · cslib에서 scout→merger 조건 비교 (rows 14–30)

#67의 비교 조건을 physlib·cslib 17문제(F014–F030)에서 돌린 결과다. 계산 증명 F011–F013은 제외했다.
모든 조건은 **새 run root에서 원본부터** 시작했다. 이전 실행의 풀이, seed, 문제별 힌트는 쓰지 않았다.

- 코드: main `a517db2`의 `experiments/final-batch-next/driver.py`. 문제당 $1이고, 모델은 driver 기본값 `gpt-6.1-sol`을 OpenAI로 직접 호출했다.
  최종 실행은 주최측이 OpenRouter로 돌리므로 비용·지연은 다를 수 있다.
- 환경: Windows PC의 WSL2(Ubuntu, 16코어, 15GB)에서 6개 환경을 준비했다(physlib v4.34.0·v4.34.1, cslib v4.30.0·v4.31.0·v4.33.1·v4.34.1).
  이를 위해 로컬 전용 변경을 썼다. main에는 넣지 않는다.
  - Linux Lean 배포본 이름
  - 환경 일부만 준비하는 `ARENA_ENV_ONLY`
  - bwrap sandbox(되돌린 09d3793)
  - lane별 compiler lock `ARENA_COMPILER_LOCK`
  - C5용 `--show-original`(`hide_original_first_scout: false`)
- 점수: 보존된 best의 J = T/T0 + H/H0로 계산했다(원본 = 2, 모든 버전 통과).
  - 거의 모든 행이 $1 비용 한도에서 `stopped`로 끝났다. `compare_conditions.py`는 `completed`만 점수에 넣으므로, 여기서는 `summarize.py`로 stopped 행도 집계했다.
- 데이터: `results.json`(조건·행별 J, 비용, 종료 사유, 평가 수). 다시 계산하려면 `python3 summarize.py`.

| 조건 | 옵션 | 평균 J (17문제) | C0·C0b 평균 대비 (paired bootstrap 95% CI) |
|---|---|---|---|
| C0 | 기본 6×3 + 22 | 0.858 | |
| C0b | C0 반복 | 0.889 | |
| C1 | `--scout-evaluations 10 --merger-evaluations 10` | 1.011 | +0.138 [+0.041, +0.252] |
| C2 | `--scout-evaluations 5 --merger-evaluations 5 --rounds 2` | **0.835** | −0.038 [−0.093, +0.021], 11/17 우세 |
| C5 | 기본 + scout-a에 원본 공개 | 0.891 | +0.017 [−0.056, +0.105] |
| C6 | `--scout-evaluations 3 --merger-until-budget` | 0.998 | +0.124 [+0.013, +0.251] |

C3·C4는 돌리지 않았다. 파일럿(F018)에서 기본 설정이 merger 3/22회째에 $1에 닿았다. physlib 문맥에서는 평가당 약 $0.05가 들기 때문이다. 이 조건에서는 C3·C4가 사실상 C0·C2와 같아진다.

## 관찰

1. **실행 간 분산이 크다.** 같은 설정의 C0와 C0b 사이 |ΔJ|는 중앙값 0.101, 최대 0.441이었다.
   조건당 1회 실행으로는 0.1 이하 차이를 구분하지 못한다.
2. **merger를 굶겨도, scout를 굶겨도 나빠진다.**
   - C1은 scout가 예산을 다 써서 merger에 거의 도달하지 못했다. F017은 개선이 0이었다.
   - C6은 scout가 줄어 출발점 다양성이 떨어졌다.
   - 둘 다 CI가 0을 넘는다. 기본 배분이 대체로 합리적이다.
3. **두 라운드(C2)는 약간 좋아 보이지만 유의하지 않다.** 2라운드 seed는 같은 실행의 1라운드 best이므로 규칙상 문제없다.
4. **scout-a에서 원본을 숨기는지(#61)는 측정 가능한 차이가 없다**(C5).
5. **같은 예산이면 반복 실행 후 best 선택이 가장 큰 변수다.** 6개 실행의 행별 최소 J 평균은 0.754다.
   단일 $1 실행(0.858)이나, 별도 runner로 문제당 약 $2.6를 쓴 결과(0.847)보다 낮다.
6. **예산 예약 때문에 덜 쓴다.** C6은 다음 요청의 최악 비용 예약 때문에 평균 $0.79에서 끝났다(`portfolio_budget_complete`).

총비용은 $98.9이고, 파일럿 F018에 $1.0을 더 썼다.

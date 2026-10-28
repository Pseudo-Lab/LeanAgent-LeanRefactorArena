# analyze(proof) 결과

컴파일과 모델 호출 없이 계산함. 예상 감소량은 토큰 수로 낸 추정치이며 컴파일 결과가 아님.

| # | 출처 | 토큰 | 길이 | 유형 | 보조 유형 | 블록 | 대상 | 1순위 대상 | 예상 감소 |
| ---: | --- | ---: | --- | --- | --- | ---: | ---: | --- | ---: |
| 1 | strata | 313 | medium | case | - | 10 | 3 | case_body B2,B3 | 17 |
| 2 | strata | 222 | short | case | - | 7 | 1 | large B3 | - |
| 3 | strata | 224 | short | case | - | 8 | 1 | large B8 | - |
| 4 | physlib | 851 | medium | have | - | 27 | 1 | large B10 | - |
| 5 | physlib | 1,372 | medium | calc | - | 12 | 1 | large B12 | - |
| 6 | physlib | 1,217 | medium | calc | - | 24 | 4 | repeat B9 | - |
| 7 | cslib | 408 | medium | case | - | 13 | 9 | case_body B8,B9 | - |
| 8 | cslib | 407 | medium | case | - | 7 | 8 | case_body B5,B6 | 11 |
| 9 | cslib | 251 | short | case | - | 8 | 4 | repeat B7,B8 | - |
| 10 | arklib | 1,463 | medium | have | - | 23 | 1 | large B11 | - |
| 11 | arklib | 1,906 | long | have | calc | 25 | 5 | repeat B15,B16 | - |
| 12 | arklib | 1,353 | medium | have | - | 33 | 2 | repeat B30 | - |
| 13 | putnambench | 1,769 | long | have | - | 3 | 9 | repeat B2 | - |
| 14 | putnambench | 1,754 | long | have | - | 5 | 4 | repeat B2 | 43 |
| 15 | putnambench | 4,085 | long | have | - | 14 | 3 | repeat B6,B7 | 807 |

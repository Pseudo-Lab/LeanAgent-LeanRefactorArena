# P07 검증 후보

101 tokens. 공식 기준 버전4.33-rc2에서 raw HB 중앙값 7,897,617, 대회 산식의 로컬 추정 점수 87.346738.

3개 요구 버전에서 전체 소스 컴파일, 타깃 공리 검사, 독립3회 측정 및 소스/로그/nonce 해시 감사를 통과했다. 공식 제출 결과는 아니다.

Typing.wf에서 얻은 local closure를 app/tapp 분기에서 직접 분해하고, canonical-form 정리의 중복 forward 탐색을 destruct로 바꿨다. 정규화는 탐색 전에 한 번 하고 Aesop 내부 simp는 끈다. 모든 증명은 같은 타깃 명제와 원래 파일 맥락을 보존한다.

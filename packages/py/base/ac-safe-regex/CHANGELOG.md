# 변경 기록

## 0.1.0

- 독립 프로젝트로 정리(3R.3): 사내 의존을 이름 + 버전 범위로 선언, 패키지별 pytest·mypy·ruff 설정과 `dev` 의존 그룹, LICENSE·CHANGELOG 추가. 동작 변경 없음.
- 성능: 매치 결과(`SafeMatch`)의 이름 묶음 값·위치를 `regs` 한 번으로 만든다(묶음마다 `span`·
  `groupdict`를 부르지 않음). `regex`는 같은 이름 묶음이 한 번호를 함께 쓰므로 값·위치는 그대로다.

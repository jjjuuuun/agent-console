# agent-console-write-budget

실행 하나가 여러 도구 묶음(예: 메모리·위키 에이전트 도구)에 함께 넘기는 쓰기 횟수 한도다. 표준 라이브러리만
쓰고 스레드 안전하다. 한도 값·사유 코드·문구는 쓰는 쪽이 정하고, 이 패키지는 세는 일만 한다.

- `WriteBudget(limit)`: `take()`가 남은 횟수가 있으면 참(한 번 씀), 없으면 거짓. `limit=None`이면 늘 참.
- `WriteBudgetLike`: `take() -> bool`만 있으면 되는 프로토콜. 도구 묶음은 이 모양만 받는다.

## 설치

```bash
pip install agent-console-write-budget
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-write-budget
```

## 최소 사용

```python
>>> from agent_console_write_budget import WriteBudget, WriteBudgetLike
>>> budget = WriteBudget(2)
>>> [budget.take() for _ in range(3)], budget.used
([True, True, False], 2)
>>> isinstance(budget, WriteBudgetLike), WriteBudget(None).take()
(True, True)

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

## 개발·재사용

이 폴더는 독립 프로젝트다. 폴더만 복사해도 아래 명령이 그대로 돈다.

```bash
uv sync                # 개발 의존(dev 그룹) 포함
uv run ruff check .
uv run mypy
uv run pytest          # README.md의 doctest 포함
```

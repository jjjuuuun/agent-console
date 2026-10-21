"""명령행: `python -m agent_console_contracts export|check <out_dir>`.

- export: JSON Schema를 생성해 쓴다.
- check: 다시 생성한 내용과 파일이 다르면 exit 1(드리프트 검사).
"""

import argparse
import sys
from collections.abc import Sequence

from .schema import check_schemas, export_schemas


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m agent_console_contracts")
    parser.add_argument("action", choices=["export", "check"])
    parser.add_argument("out_dir")
    args = parser.parse_args(argv)
    if args.action == "export":
        for path in export_schemas(args.out_dir):
            print(f"생성: {path}")
        return 0
    stale = check_schemas(args.out_dir)
    if stale:
        for path in stale:
            print(f"계약 드리프트: {path} 가 현재 모델과 다릅니다.", file=sys.stderr)
        print("`uv run poe contracts`로 다시 생성하고 결과를 커밋하세요.", file=sys.stderr)
        return 1
    print("계약 JSON Schema 최신 상태")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

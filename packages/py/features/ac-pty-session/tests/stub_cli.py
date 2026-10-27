"""PTY 테스트용 스텁 CLI(실제 도구를 부르지 않는다). 첫 인자 = 시나리오."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time


def main() -> int:
    mode = sys.argv[1]
    if mode == "echo":
        sys.stdout.write("ready> ")
        sys.stdout.flush()
        line = sys.stdin.readline().strip()
        print(f"got:{line}")
        return int(sys.argv[2]) if len(sys.argv) > 2 else 0
    if mode == "long":
        size = os.get_terminal_size(sys.stdout.fileno())
        print(f"size={size.columns}x{size.lines}")
        print("x" * 300 + "END")
        return 0
    if mode == "exit":
        print("bye")
        return int(sys.argv[2])
    if mode == "ansi":
        sys.stdout.write("\x1b[32mloading 10%\rloading 99%\x1b[0m\r\n")
        sys.stdout.write(
            "\x1b]8;;https://example.com/oauth/authorize?x=1\x1b\\open link\x1b]8;;\x1b\\\r\n"
        )
        sys.stdout.write("Paste code here if prompted > ")
        sys.stdout.flush()
        code = sys.stdin.readline().strip()
        print(f"\x1b[2K\rcode-len={len(code)}")
        return 0
    if mode == "ignore_term":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGHUP, signal.SIG_IGN)
        print("ignoring", flush=True)
        while True:
            time.sleep(0.1)
    if mode == "grandchild":
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        print(f"child={child.pid}", flush=True)
        while True:
            time.sleep(0.1)
    if mode == "env":
        print(f"VAR={os.environ.get('STUB_VAR', '<none>')} CWD={os.getcwd()}", flush=True)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())

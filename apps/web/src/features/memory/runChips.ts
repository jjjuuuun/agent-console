/** 실행 상세 요약 줄의 메모리 칩 계산(순수 함수). 범위·키·도구 이름을 모른다 — 이벤트 type의 뒤쪽 이름과 payload `status`만 본다. */
import type { RunEvent } from "@agent-console/contracts";
import { RUN_CHIPS } from "./memoryConfig";

export interface ChipCounts {
  count: number;
  failed: number;
}

export interface RunChipCounts {
  write: ChipCounts;
  read: ChipCounts;
}

/** 이 실행의 이벤트에서 쓰기·읽기 수와 실패 수. 접두가 다르거나 모르는 이름의 이벤트는 세지 않는다. */
export function countRunChips(events: readonly RunEvent[], chips = RUN_CHIPS): RunChipCounts {
  const out: RunChipCounts = { write: { count: 0, failed: 0 }, read: { count: 0, failed: 0 } };
  for (const e of events) {
    if (!e.type.startsWith(chips.typePrefix)) continue;
    const name = e.type.slice(chips.typePrefix.length);
    const bucket = chips.write.types.includes(name) ? out.write : chips.read.types.includes(name) ? out.read : undefined;
    if (bucket === undefined) continue;
    bucket.count += 1;
    const status = (e.payload ?? {})["status"];
    if (typeof status === "string" && status !== chips.okStatus) bucket.failed += 1;
  }
  return out;
}

/** 숫자 글: 상한을 넘으면 "200+". */
export function chipNumber(n: number, cap = RUN_CHIPS.cap): string {
  return n > cap ? `${cap}+` : String(n);
}

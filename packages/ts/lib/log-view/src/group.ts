import type { LogEvent } from "@agent-console/contracts/logs";

export interface MessageGroup<T> {
  key: string;
  head: T;
  children: T[];
}

export type GroupedItem<T> = { kind: "row"; row: T } | { kind: "group"; group: MessageGroup<T> };

/**
 * 같은 `thread` + 같은 `message_id`(둘 다 비어 있지 않음)인 이벤트를 한 응답으로 묶는다.
 * 연속하지 않아도 묶고, 묶음 위치는 첫 이벤트 자리다. 시간 근접 묶기는 없다. `message_id`가 없으면 묶지 않는다.
 * 묶음이 1개짜리면 일반 행으로 돌려준다.
 */
export function groupByMessage<T extends Pick<LogEvent, "thread" | "message_id">>(rows: readonly T[]): GroupedItem<T>[] {
  const groups = new Map<string, T[]>();
  for (const r of rows) {
    if (r.thread && r.message_id) {
      const k = `${r.thread}\u0000${r.message_id}`;
      const g = groups.get(k);
      if (g) g.push(r);
      else groups.set(k, [r]);
    }
  }
  const emitted = new Set<string>();
  const out: GroupedItem<T>[] = [];
  for (const r of rows) {
    if (!(r.thread && r.message_id)) {
      out.push({ kind: "row", row: r });
      continue;
    }
    const k = `${r.thread}\u0000${r.message_id}`;
    const g = groups.get(k) as T[];
    if (g.length < 2) {
      out.push({ kind: "row", row: r });
    } else if (!emitted.has(k)) {
      emitted.add(k);
      out.push({ kind: "group", group: { key: k, head: g[0] as T, children: g.slice(1) } });
    }
  }
  return out;
}

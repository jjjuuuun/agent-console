import type { LogEvent, LogTaxonomy, LogWidget } from "@agent-console/contracts/logs";

/** 테스트 전용 임의 이름. 어떤 이름이어도 동작해야 하므로 실제 출처·범주 이름을 쓰지 않는다. */
export const slotFor = (key: string): number => key.length % 8;

export function ev(partial: Partial<LogEvent> & { uid: string; seq: number }): LogEvent {
  return { source: "src-a", observed_at: 1_700_000_000, category: "cat-a", title: `title ${partial.uid}`, ...partial } as LogEvent;
}

export function events(n: number, make: (i: number) => Partial<LogEvent> = () => ({})): LogEvent[] {
  return Array.from({ length: n }, (_, i) => ev({ uid: `u${i}`, seq: i + 1, time: 1_700_000_000 + i, ...make(i) }));
}

export const taxonomy: LogTaxonomy = {
  categories: {
    "zz-bad": { label: "Bad things", tone: "danger", color: "cat-3" },
    "zz-hidden": { visible: false },
    "zz-odd": { label: "x".repeat(100), color: "not-a-token" },
  },
  order: ["zz-odd", "zz-bad"],
};

export function widget(id: string, kind: string, extra: Partial<LogWidget> = {}): LogWidget {
  return { id, kind, query: { group_by: ["dim-a"], metric: "m-a" }, options: {}, ...extra } as LogWidget;
}

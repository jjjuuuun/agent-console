import { describe, expect, it } from "vitest";
import type { LogDashboard, LogEvent, LogSourceInfo, WorkspaceSettings } from "@agent-console/contracts";
import { findReservedConflicts, reservedParams, toTaxonomyView, isErrorEvent, isHiddenEvent } from "@agent-console/log-view";
import { FILTER_FIELDS, FILTER_KEYS, SCREEN_PARAMS, SUGGEST_FROM } from "./logsConfig";
import { categoryItems, classifyEmpty, filterSessionEvents, firstUseSources, offReadingSources, paramsKey, parseRange, rangeToWindow, shouldAutoFoldFlow, archDefaultHeight, clampOr, toLaneEvents, toRequestParams, withDashboards } from "./logsLib";

const ev = (over: Partial<LogEvent> & { uid: string }): LogEvent => ({ seq: 1, source: "s", observed_at: 0, category: "c1", ...over });
const names = { search: "q", category: FILTER_KEYS.category, since: FILTER_KEYS.since, until: FILTER_KEYS.until, source: FILTER_KEYS.source, suggestFrom: SUGGEST_FROM };
const info = (id: string, over: { enabled?: boolean; reads?: boolean; def?: boolean } = {}): LogSourceInfo => ({
  descriptor: { id, title: `T-${id}`, format: "f", reads_paths: over.reads ?? false, default_enabled: over.def ?? false },
  enabled: over.enabled ?? false,
});

describe("화면 전용 URL 파라미터", () => {
  it("예약 이름은 필터 필드와 겹치지 않고 log-view 예약 목록과 같다", () => {
    expect(findReservedConflicts(FILTER_FIELDS.map((f) => f.name))).toEqual([]);
    expect([...Object.values(SCREEN_PARAMS)].sort()).toEqual([...reservedParams].sort());
  });
});

describe("기간", () => {
  it("선택지는 지금 기준 since, all은 기간 없음, 모르는 값은 기본 선택지, 사용자 지정은 그대로", () => {
    expect(rangeToWindow(parseRange("7d", "24h"), 1_000_000_000)).toEqual({ since: String(1_000_000 - 7 * 86400) });
    expect(rangeToWindow(parseRange("all", "7d"), 1000)).toEqual({});
    expect(parseRange("zzz", "24h")).toMatchObject({ kind: "option", id: "24h" });
    expect(rangeToWindow(parseRange("A..B", "7d"), 0)).toEqual({ since: "A", until: "B" });
  });
});

describe("요청 파라미터", () => {
  it("칩의 since가 기간 선택지보다 우선하고, 빈 값은 보내지 않으며, 키는 이름 순으로 안정적이다", () => {
    const p = toRequestParams({ [FILTER_KEYS.since]: "5", z: ["a", "b"], e: "" }, { limit: 10 }, { since: "1" });
    expect(p).toEqual({ [FILTER_KEYS.since]: "5", z: ["a", "b"], limit: "10" });
    expect(paramsKey(p)).toBe(paramsKey({ limit: "10", z: ["a", "b"], [FILTER_KEYS.since]: "5" }));
  });
});

describe("세션 상세 표시 필터(임의 범주·필드)", () => {
  const tax = toTaxonomyView({ categories: { zz: { tone: "danger" }, hid: { visible: false } } });
  const isErr = (e: LogEvent) => isErrorEvent(e, tax);
  const isHid = (e: LogEvent) => isHiddenEvent(e, tax);
  const events = [
    ev({ uid: "1", category: "zz", title: "깨짐", thread: "t1" }),
    ev({ uid: "2", category: "c9", title: "Alpha 호출", tool: "x-tool", thread: "t2", call_id: "k1" }),
    ev({ uid: "3", category: "hid", title: "숨김" }),
  ];
  const base = { filter: {}, names, errorsOnly: false, lanes: [], includeHidden: false };
  it("숨긴 범주는 기본으로 빠지고 토글하면 포함된다", () => {
    expect(filterSessionEvents(events, base, isErr, isHid).map((e) => e.uid)).toEqual(["1", "2"]);
    expect(filterSessionEvents(events, { ...base, includeHidden: true }, isErr, isHid)).toHaveLength(3);
  });
  it("오류만·레인·범주·검색어(대소문자 무시)·이벤트 필드 필터", () => {
    expect(filterSessionEvents(events, { ...base, errorsOnly: true }, isErr, isHid).map((e) => e.uid)).toEqual(["1"]);
    expect(filterSessionEvents(events, { ...base, lanes: ["t2"] }, isErr, isHid).map((e) => e.uid)).toEqual(["2"]);
    expect(filterSessionEvents(events, { ...base, filter: { [FILTER_KEYS.category]: ["c9", "zz"] } }, isErr, isHid)).toHaveLength(2);
    expect(filterSessionEvents(events, { ...base, filter: { q: "alpha" } }, isErr, isHid).map((e) => e.uid)).toEqual(["2"]);
    expect(filterSessionEvents(events, { ...base, filter: { [FILTER_KEYS.callId]: "k1" } }, isErr, isHid).map((e) => e.uid)).toEqual(["2"]);
  });
  it("범주 칩은 세션에 나온 범주 전부이고 분류 체계가 비어도 동작한다", () => {
    expect(categoryItems(events, events.slice(0, 1)).map((c) => [c.id, c.count, c.total])).toEqual([["zz", 1, 1], ["c9", 0, 1], ["hid", 0, 1]]);
  });
  it("짝 이벤트는 [완료 시각 - 소요, 완료 시각] 막대가 된다(서버 값만)", () => {
    const [a, b] = toLaneEvents([ev({ uid: "a", time: 10, duration_ms: 2000 }), ev({ uid: "b", time: 11 }), ev({ uid: "c" })], () => false);
    expect(a).toMatchObject({ time: 8, endTime: 10 });
    expect(b).toMatchObject({ time: 11, endTime: null });
  });
});

describe("빈 상태 판정(A/B/C)", () => {
  it("켜진 출처 0개 = A, 이벤트 없음 = B, 있음/조회 실패 = C", () => {
    expect(classifyEmpty([info("a")], true)).toBe("A");
    expect(classifyEmpty([], true)).toBe("A");
    expect(classifyEmpty([info("a", { enabled: true })], false)).toBe("B");
    expect(classifyEmpty([info("a", { enabled: true })], true)).toBe("C");
    expect(classifyEmpty([info("a", { enabled: true })], undefined)).toBe("C");
  });
  it("첫 사용 카드 순서: 속성(reads_paths && !default_enabled)만 본다", () => {
    const list = [info("p"), info("q", { reads: true }), info("r", { enabled: true }), info("s", { reads: true, def: true })];
    expect(firstUseSources(list).map((s) => s.descriptor.id)).toEqual(["q", "p", "s"]);
    expect(offReadingSources(list).map((s) => s.descriptor.id)).toEqual(["q", "s"]);
  });
});

describe("대시보드 저장 병합", () => {
  it("한 위젯만 바꿔 저장해도 모르는 위젯·키·다른 설정 키가 그대로 남는다", () => {
    const server: WorkspaceSettings = {
      chat: { reply_display: "x" } as never,
      logs: {
        sources: [{ id: "a", enabled: true }],
        extra_logs_key: 1,
        dashboards: [
          {
            id: "d1",
            title: "T",
            future: { a: 1 },
            widgets: [
              { id: "w1", kind: "unknown-kind", query: { metric: "m", extra_q: 2 }, options: { w: 4, keepme: true }, wfuture: "z" },
              { id: "w2", kind: "k", query: { metric: "m2", group_by: ["g"] }, options: { w: 6, h: 4, owned: 1 } },
            ],
          } as LogDashboard,
        ],
      },
    };
    const edited = structuredClone(server.logs?.dashboards ?? []) as LogDashboard[];
    // 편집기가 알 수 있는 부분만 담은 사본(알 수 없는 키가 빠진 상태)을 만든다
    const lean: LogDashboard[] = [{ id: "d1", title: "T2", widgets: [{ id: "w1", kind: "unknown-kind", query: { metric: "m" }, options: { w: 4 } }, { ...(edited[0]!.widgets![1] as object), id: "w2", kind: "k", query: { metric: "m2", group_by: ["g"] }, options: { w: 6, h: 5 } }] }];
    const out = withDashboards(server, lean, { ownedOptionKeys: (k) => (k === "k" ? ["owned"] : []) });
    expect(out.chat).toEqual(server.chat);
    expect(out.logs?.sources).toEqual(server.logs?.sources);
    expect(out.logs?.["extra_logs_key"]).toBe(1);
    const d = out.logs?.dashboards?.[0] as Record<string, unknown>;
    expect(d["future"]).toEqual({ a: 1 });
    const w = (d["widgets"] as Record<string, unknown>[])[0] as Record<string, unknown>;
    expect(w["wfuture"]).toBe("z");
    expect((w["query"] as Record<string, unknown>)["extra_q"]).toBe(2);
    expect((w["options"] as Record<string, unknown>)["keepme"]).toBe(true);
    // 편집기가 소유한 옵션 키는 지운 값이 되살아나지 않는다
    expect(((d["widgets"] as { options: Record<string, unknown> }[])[1] as { options: Record<string, unknown> }).options).toEqual({ w: 6, h: 5 });
  });
});

describe("흐름 패널 자동 접기 (5R.21)", () => {
  const base = { minRows: 8, rowHeight: 32, collapsed: false, userOpened: false } as const;
  it("표 높이가 최소 행 수 분량보다 작을 때만 접는다", () => {
    expect(shouldAutoFoldFlow({ ...base, tableHeight: 255 })).toBe(true);
    expect(shouldAutoFoldFlow({ ...base, tableHeight: 256 })).toBe(false);
  });
  it("이미 접혀 있거나 사용자가 직접 펴 둔 상태면 접지 않는다", () => {
    expect(shouldAutoFoldFlow({ ...base, tableHeight: 100, collapsed: true })).toBe(false);
    expect(shouldAutoFoldFlow({ ...base, tableHeight: 100, userOpened: true })).toBe(false);
  });
  it("clampOr: 범위로 자르고 숫자가 아니면 기본값", () => {
    expect(clampOr(10, 96, 480, 240)).toBe(96);
    expect(clampOr(900, 96, 480, 240)).toBe(480);
    expect(clampOr(Number.NaN, 96, 480, 240)).toBe(240);
  });
  it("archDefaultHeight: min(기본, 뷰포트 − 표 N행 − 머리), 하한 floor", () => {
    const base = { preferred: 400, floor: 240, tableRows: 4, rowHeight: 32, chrome: 400 };
    expect(archDefaultHeight({ ...base, viewportHeight: 1200 })).toBe(400);
    expect(archDefaultHeight({ ...base, viewportHeight: 768 })).toBe(240);
    expect(archDefaultHeight({ ...base, viewportHeight: 1000 })).toBe(400);
    expect(archDefaultHeight({ ...base, viewportHeight: 880 })).toBe(352);
    expect(archDefaultHeight({ ...base, viewportHeight: 300 })).toBe(240);
  });
});

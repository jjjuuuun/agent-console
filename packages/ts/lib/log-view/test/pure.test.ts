import { describe, expect, it } from "vitest";
import type { LogWidget } from "@agent-console/contracts/logs";
import type { Trace } from "@agent-console/contracts";
import {
  buildFilterQuery, buildScreenSearch, clipTraceAt, createLocalStorageSavedFilters, duplicateWidget, findReservedConflicts, formatDurationMs, formatRelativeTime, formatTokensShort,
  groupByMessage, indexOfSeq, isErrorEvent, isHiddenEvent, layoutFlow, moveWidget, nextSpeed, orderCategories, playbackDelay, preserveUnknown, preserveUnknownDashboards, reservedParams, resizeWidget,
  seqAtIndex, shortPath, sortEvents, splitSearchParams, toTaxonomyView, visibleThrough, widgetSize, colorFor, validateQuery,
} from "../src";
import { ev, slotFor, taxonomy, widget } from "./fixtures";

describe("재생 순서", () => {
  it("(time, seq) 오름차순이고 time이 없으면 앞 이벤트 시각을 물려받아 제자리", () => {
    const sorted = sortEvents([
      { seq: 1, time: 10 },
      { seq: 2, time: 5 },
      { seq: 3 },
      { seq: 4, time: 5 },
    ]);
    // seq 3은 seq 2(시각 5)를 물려받아 seq 2 뒤, seq 4 앞.
    expect(sorted.map((e) => e.seq)).toEqual([2, 3, 4, 1]);
  });
  it("같은 시각은 seq 순, 입력을 바꾸지 않는다", () => {
    const input = [{ seq: 3, time: 1 }, { seq: 1, time: 1 }];
    expect(sortEvents(input).map((e) => e.seq)).toEqual([1, 3]);
    expect(input[0]?.seq).toBe(3);
  });
  it("visibleThrough·indexOfSeq·seqAtIndex", () => {
    const s = sortEvents([{ seq: 1, time: 1 }, { seq: 2, time: 2 }, { seq: 3, time: 3 }]);
    expect(visibleThrough(s, -1)).toEqual([]);
    expect(visibleThrough(s, 1)).toHaveLength(2);
    expect(indexOfSeq(s, 2)).toBe(1);
    expect(indexOfSeq(s, undefined)).toBe(2);
    expect(indexOfSeq(s, 99)).toBe(2);
    expect(seqAtIndex(s, 2)).toBeUndefined();
    expect(seqAtIndex(s, 0)).toBe(1);
  });
  it("대기 시간 d = min(gap, cap)/speed, 하한 16ms", () => {
    expect(playbackDelay(10_000, 1, true)).toBe(2000);
    expect(playbackDelay(10_000, 1, false)).toBe(10_000);
    expect(playbackDelay(60_000, 1, false)).toBe(30_000);
    expect(playbackDelay(1000, 10, false)).toBe(100);
    expect(playbackDelay(0, 30, true)).toBe(16);
  });
  it("nextSpeed는 끝에서 멈추고 목록에 없는 값은 가까운 칸 기준", () => {
    expect(nextSpeed([1, 2, 5], 2, 1)).toBe(5);
    expect(nextSpeed([1, 2, 5], 5, 1)).toBe(5);
    expect(nextSpeed([1, 2, 5], 1, -1)).toBe(1);
    expect(nextSpeed([1, 2, 5], 1.9, 1)).toBe(5);
  });
});

describe("clipTraceAt", () => {
  const trace = {
    run_id: "r",
    spans: [
      { id: "a", kind: "k", started_at: 10, ended_at: 20, status: "done" },
      { id: "b", kind: "k", parent_id: "a", started_at: 15, ended_at: 30, status: "done" },
      { id: "c", kind: "k", started_at: 40, ended_at: 50 },
      { id: "d", kind: "k" },
    ],
    links: [{ source: "a", target: "b" }, { source: "a", target: "c" }],
  } as Trace;
  it("시각 이전에 시작한 span만 남기고 진행 중은 running으로", () => {
    const out = clipTraceAt(trace, 18);
    expect(out.spans?.map((s) => s.id)).toEqual(["a", "b"]);
    expect(out.spans?.[0]).toMatchObject({ id: "a", status: "running", ended_at: null });
    expect(out.spans?.[1]?.status).toBe("running");
    expect(out.links).toEqual([{ source: "a", target: "b" }]);
    expect(trace.spans?.[0]?.status).toBe("done"); // 원본 불변
  });
  it("끝난 span은 그대로, 위치가 끝(null)이면 원본", () => {
    expect(clipTraceAt(trace, 25).spans?.[0]?.status).toBe("done");
    expect(clipTraceAt(trace, null)).toBe(trace);
  });
});

describe("분류 체계", () => {
  const view = toTaxonomyView(taxonomy);
  it("오류 판정은 tone=danger만 본다(이름·status 비교 없음)", () => {
    expect(isErrorEvent({ category: "zz-bad" }, view)).toBe(true);
    expect(isErrorEvent({ category: "other", tags: ["zz-bad"] }, view)).toBe(true);
    expect(isErrorEvent({ category: "failed-looking-name" }, view)).toBe(false);
    expect(isErrorEvent({ category: "zz-bad" }, toTaxonomyView(undefined))).toBe(false);
    expect(isErrorEvent({ category: "zz-bad" }, toTaxonomyView({ categories: { "zz-bad": {} } }))).toBe(false);
  });
  it("없는 범주는 이름 = id, 숨김 판정", () => {
    expect(view.get("nope")).toMatchObject({ name: "nope", visible: true });
    expect(isHiddenEvent({ category: "zz-hidden" }, view)).toBe(true);
    expect(isHiddenEvent({ category: "nope" }, view)).toBe(false);
  });
  it("색: 토큰이면 --ac-cat-N, 모르는 색·없는 범주는 해시 슬롯", () => {
    expect(colorFor("zz-bad", view, slotFor)).toBe("var(--ac-cat-3)");
    expect(colorFor("zz-odd", view, slotFor)).toBe(`var(--ac-cat-${(slotFor("zz-odd") % 8) + 1})`);
    expect(colorFor("nope", undefined, () => 11)).toBe("var(--ac-cat-4)");
  });
  it("칩 순서: 분류 체계 순서 -> 개수 내림차순(total 우선)", () => {
    const out = orderCategories([{ id: "b", count: 1 }, { id: "zz-bad", count: 1 }, { id: "a", count: 5 }, { id: "zz-odd", count: 0 }, { id: "c", count: 1, total: 9 }], view);
    expect(out.map((i) => i.id)).toEqual(["zz-odd", "zz-bad", "c", "a", "b"]);
  });
});

describe("groupByMessage", () => {
  it("thread+message_id가 모두 있을 때만 떨어져 있어도 묶고 시간 근접 묶기는 없다", () => {
    const rows = [
      { thread: "t", message_id: "m1", n: 1 },
      { thread: "t", n: 2 },
      { thread: "t", message_id: "m1", n: 3 },
      { thread: "u", message_id: "m1", n: 4 },
      { message_id: "m1", n: 5 },
    ];
    const out = groupByMessage(rows);
    expect(out).toHaveLength(4);
    expect(out[0]).toMatchObject({ kind: "group", group: { head: { n: 1 }, children: [{ n: 3 }] } });
    expect(out.slice(1).every((i) => i.kind === "row")).toBe(true);
  });
});

describe("필터 쿼리", () => {
  it("예약 이름은 필터로 보내지 않고 화면 전용으로 보존한다", () => {
    const r = splitSearchParams("a=1&a=2&b=x&through=5&lane=l1&lane=l2&view=v&range=7d&tab=t&empty=");
    expect(r.filter).toEqual({ a: ["1", "2"], b: "x" });
    expect(r.screen).toEqual({ through: ["5"], lane: ["l1", "l2"], view: ["v"], range: ["7d"], tab: ["t"] });
  });
  it("fields가 있으면 모르는 이름을 unknown으로 알리되 보낸다", () => {
    const r = splitSearchParams("a=1&zzz=2", { fields: [{ name: "a", label: "A", input: "text" }] });
    expect(r.unknown).toEqual(["zzz"]);
    expect(r.filter).toEqual({ a: "1", zzz: "2" });
  });
  it("buildFilterQuery는 예약 이름을 제외하고 반복 키로 다중 값", () => {
    const q = buildFilterQuery({ a: ["1", "2"], through: "9", b: "" });
    expect(q.toString()).toBe("a=1&a=2");
    expect(buildScreenSearch({ a: "1" }, { through: ["3"] }).toString()).toBe("a=1&through=3");
  });
  it("충돌 테스트: 서버 필터 이름이 예약과 겹치면 알린다", () => {
    expect(findReservedConflicts(["q", "through", "x"])).toEqual(["through"]);
    expect(findReservedConflicts(["session", "category", "since", "until", "limit"])).toEqual([]);
    expect([...reservedParams]).toEqual(["through", "lane", "view", "range", "tab"]);
  });
});

describe("즐겨찾는 필터 저장소", () => {
  const mem = () => {
    const data = new Map<string, string>();
    return { getItem: (k: string) => data.get(k) ?? null, setItem: (k: string, v: string) => void data.set(k, v) };
  };
  it("저장·덮어쓰기·삭제, 이름은 40자까지", () => {
    const store = createLocalStorageSavedFilters("k", mem());
    store.save({ name: "a", value: { x: "1" } });
    store.save({ name: "a", value: { x: "2" } });
    store.save({ name: "n".repeat(60), value: {} });
    expect(store.list()).toHaveLength(2);
    expect(store.list().find((f) => f.name === "a")?.value).toEqual({ x: "2" });
    expect(store.list().some((f) => f.name.length === 40)).toBe(true);
    store.remove("a");
    expect(store.list()).toHaveLength(1);
  });
  it("저장소가 실패하거나 깨져도 던지지 않는다", () => {
    const broken = { getItem: () => "{not json", setItem: () => { throw new Error("quota"); } };
    const store = createLocalStorageSavedFilters("k", broken);
    expect(store.list()).toEqual([]);
    expect(() => store.save({ name: "a", value: {} })).not.toThrow();
  });
});

describe("대시보드 배치", () => {
  const ws = (sizes: [number, number][]): LogWidget[] => sizes.map(([w, h], i) => widget(`w${i}`, "k", { options: { w, h } }));
  it("순서 + w·h로 흐르고 줄이 차면 다음 줄", () => {
    const p = layoutFlow(ws([[6, 4], [6, 2], [6, 4]]));
    expect(p.map((x) => [x.col, x.row, x.w, x.h])).toEqual([[0, 0, 6, 4], [6, 0, 6, 2], [0, 4, 6, 4]]);
  });
  it("6열에서는 ceil(w/2), 최소 3", () => {
    const p = layoutFlow(ws([[12, 4], [5, 2], [3, 2]]), 6);
    expect(p.map((x) => [x.col, x.row, x.w])).toEqual([[0, 0, 6], [0, 4, 3], [3, 4, 3]]);
  });
  it("크기 기본값·클램프", () => {
    expect(widgetSize({ options: {} })).toEqual({ w: 6, h: 4 });
    expect(widgetSize({ options: {} }, { w: 3, h: 2 })).toEqual({ w: 3, h: 2 });
    expect(widgetSize({ options: { w: 99, h: 0 } })).toEqual({ w: 12, h: 2 });
    expect(widgetSize({ options: { w: "x" } })).toEqual({ w: 6, h: 4 });
  });
  it("move·resize는 다른 위젯 객체와 알 수 없는 키를 그대로 둔다", () => {
    const list = ws([[6, 4], [6, 4], [6, 4]]);
    const moved = moveWidget(list, "w0", 2);
    expect(moved.map((w) => w.id)).toEqual(["w1", "w2", "w0"]);
    expect(moved[0]).toBe(list[1]);
    expect(moveWidget(list, "nope", 0)).toBe(list);
    const odd = widget("x", "k", { options: { w: 6, h: 4, keep: { deep: [1] } }, extra: 1 } as Partial<LogWidget>);
    const resized = resizeWidget([odd, list[0] as LogWidget], "x", { w: 20, h: 1 });
    expect(resized[0]?.options).toEqual({ w: 12, h: 2, keep: { deep: [1] } });
    expect((resized[0] as Record<string, unknown>)["extra"]).toBe(1);
    expect(resized[1]).toBe(list[0]);
  });
  it("복제는 깊은 복사", () => {
    const list = ws([[6, 4]]);
    const out = duplicateWidget(list, "w0", "copy");
    expect(out.map((w) => w.id)).toEqual(["w0", "copy"]);
    expect(out[1]?.query).not.toBe(out[0]?.query);
  });
  it("임의 키를 가진 대시보드에서 위젯 하나만 바꿔도 나머지는 바이트까지 같다", () => {
    const prev = [
      { id: "d1", title: "T", future_key: { a: 1 }, widgets: [widget("a", "k", { extra: [1, 2] } as Partial<LogWidget>), widget("b", "unknown-kind", { options: { w: 3, h: 2, zz: "q" } })] },
      { id: "d2", title: "U", widgets: [] },
    ] as never[];
    const original = JSON.stringify(prev);
    // 편집기가 알 수 없는 키를 모르고 위젯을 다시 만든 경우의 안전망
    const edited = [
      { id: "d1", title: "T2", widgets: [{ id: "a", kind: "k", query: { group_by: ["dim-a"], metric: "m-b" }, options: { w: 6, h: 4 } }, ((prev[0] as unknown) as { widgets: LogWidget[] }).widgets[1] as LogWidget] },
      prev[1],
    ] as never[];
    const out = preserveUnknownDashboards(prev, edited);
    expect(JSON.stringify(prev)).toBe(original);
    expect(JSON.stringify(out[1])).toBe(JSON.stringify(prev[1]));
    expect((out[0] as Record<string, unknown>)["future_key"]).toEqual({ a: 1 });
    const a = (out[0] as { widgets: Record<string, unknown>[] }).widgets[0] as Record<string, unknown>;
    expect(a["extra"]).toEqual([1, 2]);
    expect((a["query"] as { metric: string }).metric).toBe("m-b");
    expect(JSON.stringify((out[0] as { widgets: unknown[] }).widgets[1])).toBe(JSON.stringify(((prev[0] as unknown) as { widgets: unknown[] }).widgets[1]));
  });
  it("preserveUnknown: 편집기가 소유한 옵션 키는 지워진 채로 둔다", () => {
    const prev = [widget("a", "k", { options: { w: 6, h: 4, limit: 5, other: 1 } })];
    const next = [widget("a", "k", { options: { w: 6, h: 4 } })];
    const out = preserveUnknown(prev, next, { ownedOptionKeys: () => ["limit"] });
    expect(out[0]?.options).toEqual({ w: 6, h: 4, other: 1 });
  });
  it("validateQuery는 차원 개수와 시간 차원만 본다", () => {
    const shape = { groupBy: { min: 1, max: 2 }, timeFirst: true };
    expect(validateQuery(shape, [], new Set(["t"]))).toEqual({ ok: false, reason: "count" });
    expect(validateQuery(shape, ["a"], new Set(["t"]))).toEqual({ ok: false, reason: "timeFirst" });
    expect(validateQuery(shape, ["a"], undefined)).toEqual({ ok: true }); // 시간 차원 정보가 없으면 검증 생략
    expect(validateQuery(shape, ["t", "a"], new Set(["t"]))).toEqual({ ok: true });
  });
});

describe("서식", () => {
  it("상대 시각·소요·토큰·경로", () => {
    expect(formatRelativeTime(83_456)).toBe("+1:23.456");
    expect(formatRelativeTime(3_723_400)).toBe("+1:02:03.4");
    expect(formatDurationMs(842)).toBe("842ms");
    expect(formatDurationMs(12_300)).toBe("12.3초");
    expect(formatDurationMs(125_000)).toBe("2분 05초");
    expect(formatTokensShort(999)).toBe("999");
    expect(formatTokensShort(4100)).toBe("4.1k");
    expect(formatTokensShort(1_200_000)).toBe("1.2M");
    expect(shortPath("/a/b/c/d/e")).toBe("…/d/e");
    expect(shortPath("a/b")).toBe("a/b");
  });
  it("이벤트 도우미가 입력을 만든다", () => {
    expect(ev({ uid: "x", seq: 1 }).uid).toBe("x");
  });
});

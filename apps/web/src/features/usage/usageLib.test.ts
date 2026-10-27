import { describe, expect, it } from "vitest";
import type { TokenRollupRow, UsageWindowSnapshot } from "@agent-console/contracts";
import { aggregateRollup, buildIndicatorItems, buildWindowGroups, indicatorFill, pickColorRule, remainingPercent, usedPercent, filterRollupByDays, formatRemaining, hasValue, isStaleObservation, resetState, canRefreshNow, windowDisplayName, groupSetupSnippets } from "./usageLib";

// 창 이름·출처 id는 임의 값이다. 코드에 고정된 목록이 없다는 것이 이 테스트의 전제다.
const snap = (source: string, window: string, observed: number, extra: Partial<UsageWindowSnapshot> = {}): UsageWindowSnapshot => ({ source, window, observed_at: observed, ...extra });
const official = (id: string) => id === "src-off";

describe("대표값 선택", () => {
  const list = [snap("src-obs", "w-a", 200, { used_ratio: 0.5 }), snap("src-off", "w-a", 100, { used_ratio: 0.3 }), snap("src-obs", "w-b", 50, { status: "allowed" })];
  it("기본: 가장 최근의 공식 값 → 공식이 없으면 가장 최근 값", () => {
    const groups = buildWindowGroups(list, [], official);
    expect(groups.map((g) => g.window)).toEqual(["w-a", "w-b"]);
    expect(groups[0]?.primary.source).toBe("src-off");
    expect(groups[0]?.rule).toBe("recent-official");
    expect(groups[0]?.others.map((s) => s.source)).toEqual(["src-obs"]);
    expect(groups[1]?.rule).toBe("recent");
  });
  it("설정 순서가 있으면 그 순서에서 값이 있는 첫 출처", () => {
    const g = buildWindowGroups(list, ["src-none", "src-obs", "src-off"], official)[0]!;
    expect(g.primary.source).toBe("src-obs");
    expect(g.rule).toBe("order");
    expect(g.fellBack).toBe(false);
  });
  it("순서의 출처에 값이 없으면 기본 규칙으로 대신하고 그 사실을 표시한다", () => {
    const g = buildWindowGroups(list, ["src-none"], official)[0]!;
    expect(g.primary.source).toBe("src-off");
    expect(g.fellBack).toBe(true);
  });
  it("같은 출처의 같은 창은 가장 최근 관측만 쓴다", () => {
    const g = buildWindowGroups([snap("s", "w", 1, { used_ratio: 0.1 }), snap("s", "w", 9, { used_ratio: 0.9 })], [], () => false)[0]!;
    expect(g.primary.used_ratio).toBe(0.9);
    expect(g.others).toEqual([]);
  });
  it("값이 하나도 없는 스냅샷은 hasValue=false", () => {
    expect(hasValue(snap("s", "w", 1))).toBe(false);
    expect(hasValue(snap("s", "w", 1, { used_ratio: 0 }))).toBe(true);
  });
});

describe("오래된 관측·초기화 시각", () => {
  it("stale_after_seconds가 null이면 절대 오래됨으로 판정하지 않는다", () => {
    expect(isStaleObservation(0, 1_000_000, null)).toBe(false);
    expect(isStaleObservation(0, 1_000_000, undefined)).toBe(false);
    expect(isStaleObservation(0, 1000, 600)).toBe(true);
    expect(isStaleObservation(500, 1000, 600)).toBe(false);
  });
  it("resets_at 상태는 설정과 무관한 사실", () => {
    expect(resetState(undefined, 100)).toBe("unknown");
    expect(resetState(200, 100)).toBe("future");
    expect(resetState(50, 100)).toBe("passed");
  });
  it("남은 시간 문구", () => {
    expect(formatRemaining(2 * 3600 + 14 * 60)).toBe("2시간 14분");
    expect(formatRemaining(3 * 86400 + 4 * 3600)).toBe("3일 4시간");
    expect(formatRemaining(30)).toBe("1분 미만");
  });
});

describe("토큰 집계", () => {
  const row = (extra: Partial<TokenRollupRow> & { usage: TokenRollupRow["usage"] }): TokenRollupRow => ({ ...extra });
  const rows = [
    row({ agent_id: "a1", day: "2026-10-14", usage: { input_tokens: 90, output_tokens: 30, total_tokens: 120 } }),
    row({ agent_id: "a1", day: "2026-10-15", usage: { input_tokens: 10, output_tokens: 5, total_tokens: 15 } }),
    row({ agent_id: "a2", day: "2026-10-15", usage: { total_tokens: 54 }, precision: "총 토큰만" }),
  ];
  it("차원별로 다시 합치고 합계 내림차순, 입력/출력이 없는 행은 구분 없음", () => {
    const lines = aggregateRollup(rows, "agent_id");
    expect(lines.map((l) => [l.value, l.total, l.input, l.output])).toEqual([
      ["a1", 135, 100, 35],
      ["a2", 54, undefined, undefined],
    ]);
    expect(lines[1]?.precision).toEqual(["총 토큰만"]);
    expect(lines[1]?.partialSplit).toBe(true);
    expect(aggregateRollup(rows, "day").map((l) => l.value)).toEqual(["2026-10-14", "2026-10-15"]);
  });
  it("기간 필터는 날짜 문자열 기준", () => {
    const today = new Date(2026, 9, 15);
    expect(filterRollupByDays(rows, 1, today)).toHaveLength(2);
    expect(filterRollupByDays(rows, 7, today)).toHaveLength(3);
    expect(filterRollupByDays(rows, null, today)).toHaveLength(3);
  });
});

// ---------------------------------------------------------------- 사용량 표시기 순수 함수
describe("표시기: 남음 계산과 색 규칙", () => {
  it("사용 + 남음이 100이 되고 한도를 넘으면 남음 0", () => {
    expect(usedPercent(0.625)).toBe(63);
    expect(remainingPercent(0.625)).toBe(37);
    expect(usedPercent(0.375) + remainingPercent(0.375)).toBe(100);
    expect(remainingPercent(1.2)).toBe(0);
  });
  it("가장 큰 at 이하 규칙 하나, 규칙이 없으면 undefined", () => {
    const rules = [{ at: 0.5, tone: "t-a" }, { at: 0.9, tone: "t-b" }, { at: 0.7, tone: "t-c" }];
    expect(pickColorRule(rules, 0.4)).toBeUndefined();
    expect(pickColorRule(rules, 0.75)?.tone).toBe("t-c");
    expect(pickColorRule(rules, 1)?.tone).toBe("t-b");
    expect(pickColorRule([], 1)).toBeUndefined();
    expect(pickColorRule(undefined, 1)).toBeUndefined();
  });
});

describe("표시기: 항목 만들기", () => {
  const mk = (over: Partial<UsageWindowSnapshot>): UsageWindowSnapshot => ({ source: "s1", window: "w-a", observed_at: 1000, ...over });
  const base = { labels: { "w-b": "이름 비" }, nowSec: 2000, staleAfterSeconds: null, colorRules: [] as { at: number; tone: string }[] };
  const groups = buildWindowGroups(
    [mk({ window: "w-a", used_ratio: 0.63 }), mk({ window: "w-b", status: "ok-ish" }), mk({ window: "w-c", used_tokens: 5 }), mk({ window: "w-d" })],
    [],
    () => false,
  );

  it("windows가 비면 묶음 순서의 앞 maxItems개", () => {
    const items = buildIndicatorItems({ ...base, groups, windows: [], maxItems: 2 });
    expect(items.map((i) => i.window)).toEqual(["w-a", "w-b"]);
    expect(items[0]).toMatchObject({ kind: "ratio", used: 63, remaining: 37 });
    expect(items[1]).toMatchObject({ kind: "status", name: "이름 비" });
  });
  it("windows가 있으면 그 순서대로, 관측 없는 창도 항목으로 남긴다", () => {
    const items = buildIndicatorItems({ ...base, groups, windows: ["w-c", "w-x", "w-d"], maxItems: 1 });
    expect(items.map((i) => [i.window, i.kind, i.observed])).toEqual([["w-c", "tokens", true], ["w-x", "none", false], ["w-d", "none", true]]);
  });
  it("오래됨은 설정이 숫자일 때만, 초기화 지남과 한도 초과, 규칙 적용", () => {
    const g = buildWindowGroups([mk({ used_ratio: 1.2, resets_at: 1500, observed_at: 1000 })], [], () => false);
    const off = buildIndicatorItems({ ...base, groups: g, windows: [], maxItems: 1 })[0]!;
    expect(off.stale).toBe(false);
    const on = buildIndicatorItems({ ...base, groups: g, windows: [], maxItems: 1, staleAfterSeconds: 60, colorRules: [{ at: 1, tone: "t-z" }] })[0]!;
    expect(on).toMatchObject({ stale: true, reset: "passed", overLimit: true, remaining: 0, rule: { tone: "t-z" } });
  });
  it("게이지 채움은 값 방향을 따르고 사용률이 없으면 undefined", () => {
    const [a, b] = buildIndicatorItems({ ...base, groups, windows: [], maxItems: 2 });
    expect(indicatorFill(a!, "remaining")).toBeCloseTo(0.37);
    expect(indicatorFill(a!, "used")).toBeCloseTo(0.63);
    expect(indicatorFill(b!, "used")).toBeUndefined();
  });
});

describe("표시기: 값 없는 창이 값 있는 창을 밀어내지 않는다 (5.2R D1 회귀)", () => {
  // 실서버 재현: 공식 run-events 창(사용률)이 뒤에 오고, 로컬 로그 창(사용률 없음)이 앞에 온다.
  const snaps: UsageWindowSnapshot[] = [
    { source: "src-local", window: "w-local-5", observed_at: 100, used_ratio: null, used_tokens: 0, status: "idle" },
    { source: "src-local", window: "w-local-7", observed_at: 100, used_ratio: null, used_tokens: 576 },
    { source: "src-off", window: "w-5", observed_at: 200, used_ratio: 0.42, status: "allowed" },
    { source: "src-off", window: "w-7", observed_at: 200, used_ratio: 0.81, status: "allowed_warning" },
  ];
  const args = { labels: {}, nowSec: 300, staleAfterSeconds: null, colorRules: [], windows: [] as string[], maxItems: 2 };
  it("windows가 비면 공식 값이 있는 창이 먼저 뽑힌다(사이드바 5h 42% / 7d 81%)", () => {
    const groups = buildWindowGroups(snaps, [], (id) => id === "src-off");
    const items = buildIndicatorItems({ ...args, groups });
    expect(items.map((i) => [i.window, i.kind, i.used])).toEqual([["w-5", "ratio", 42], ["w-7", "ratio", 81]]);
  });
  it("공식 값 > 그 밖의 값 > 값 없음, 같은 순위는 묶음 순서", () => {
    const g = buildWindowGroups([{ source: "s", window: "w-none", observed_at: 1 }, snaps[1]!, snaps[0]!, snaps[2]!], [], (id) => id === "src-off");
    expect(buildIndicatorItems({ ...args, groups: g, maxItems: 4 }).map((i) => i.window)).toEqual(["w-5", "w-local-7", "w-local-5", "w-none"]);
    const empty = buildWindowGroups([{ source: "s", window: "w-x", observed_at: 1 }, { source: "s", window: "w-y", observed_at: 1 }], [], () => false);
    expect(buildIndicatorItems({ ...args, groups: empty }).map((i) => i.window)).toEqual(["w-x", "w-y"]);
  });
  it("같은 창을 여러 출처가 주면 사용량 화면 카드와 같은 대표 출처의 값을 쓴다", () => {
    const both = [...snaps, { source: "src-obs", window: "w-5", observed_at: 250, used_ratio: 0.1 }];
    const groups = buildWindowGroups(both, [], (id) => id === "src-off");
    const item = buildIndicatorItems({ ...args, groups }).find((i) => i.window === "w-5");
    expect(item).toMatchObject({ source: "src-off", used: 42 });
  });
});

describe("수동 새로 고침 연타 방지", () => {
  it("마지막 시각이 없거나 간격이 지났으면 허용, 간격 안이면 막는다", () => {
    expect(canRefreshNow(10_000, 0, 5_000)).toBe(true);
    expect(canRefreshNow(10_000, 5_000, 5_000)).toBe(true);
    expect(canRefreshNow(10_000, 5_001, 5_000)).toBe(false);
  });
});

describe("windowDisplayName·groupSetupSnippets", () => {
  it("사용자 이름 → 출처가 준 이름 → 출처 제목 + id(_는 공백) → id", () => {
    expect(windowDisplayName("five_hour", { five_hour: "내 이름" }, { title: "5시간" }, "출처")).toBe("내 이름");
    expect(windowDisplayName("five_hour", {}, { title: "5시간" }, "출처")).toBe("5시간");
    expect(windowDisplayName("local_five_hour", {}, undefined, "로컬 추정")).toBe("로컬 추정 local five hour");
    expect(windowDisplayName("local_five_hour", {}, undefined)).toBe("local five hour");
  });
  it("조각은 제목별로 묶이고 처음 나온 순서를 지킨다", () => {
    const sn = (id: string, title: string, shell: string) => ({ id, title, shell, language: "", text: id });
    const g = groupSetupSnippets([sn("a", "A", ""), sn("b1", "B", "bash"), sn("b2", "B", "powershell")]);
    expect(g.map((x) => [x.title, x.items.length])).toEqual([["A", 1], ["B", 2]]);
  });
});

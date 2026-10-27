import { describe, expect, it } from "vitest";
import { abbreviateNumber, compareMetricValue, formatDurationMs, formatMetric, metricPieces, sumMetrics } from "./format";
import { defaultMessages } from "./messages";

const m = defaultMessages;
const obs = (value: number) => ({ status: "observed" as const, value });

describe("formatMetric", () => {
  it("관측: 횟수 n회(천 단위 쉼표), 0도 '0회'", () => {
    expect(formatMetric(obs(1204), m, { name: "count" }).text).toBe("1,204회");
    const zero = formatMetric(obs(0), m, { name: "count" });
    expect(zero.text).toBe("0회");
    expect(zero.value).toBe(0);
    expect(zero.missing).toBe(false);
  });
  it("칩(compact): 숫자만, 10,000 이상은 12.4k", () => {
    expect(formatMetric(obs(20), m, { name: "count", compact: true }).text).toBe("20");
    expect(formatMetric(obs(12400), m, { name: "count", compact: true }).text).toBe("12.4k");
  });
  it("토큰 41k·소요 1.2s/340ms·오류 n, 풀어 쓴 값은 전체", () => {
    const t = formatMetric(obs(41203), m, { name: "tokens" });
    expect(t.text).toBe("41.2k");
    expect(t.long).toBe("토큰 41,203");
    expect(t.aria).toBe("토큰 41.2k");
    expect(formatMetric(obs(900), m, { name: "tokens" }).text).toBe("900");
    expect(formatMetric(obs(1200), m, { name: "duration" }).text).toBe("1.2s");
    expect(formatMetric(obs(340), m, { name: "duration" }).text).toBe("340ms");
    expect(formatMetric(obs(1200), m, { name: "duration" }).aria).toBe("소요 1.2초");
    expect(formatMetric(obs(3), m, { name: "errors" }).text).toBe("오류 3");
    expect(formatDurationMs(12000, m)).toBe("12s");
  });
  it("추정: 값 뒤에 '추정', 늘 추정인 지표(inferred_duration)도", () => {
    const a = formatMetric({ status: "inferred", value: 1200 }, m, { name: "duration" });
    expect(a).toMatchObject({ text: "~1.2s 추정", aria: "소요 1.2초 추정", inferred: true });
    const b = formatMetric(obs(1200), m, { name: "inferred_duration" });
    expect(b.inferred).toBe(true);
    expect(b.text).toContain("추정");
  });
  it("수집 안 됨: '–', 0이 아니다(value null)", () => {
    for (const metric of [{ status: "not_collected" as const, value: null }, { status: "not_collected" as const }, { status: "observed" as const, value: null }]) {
      const r = formatMetric(metric, m, { name: "tokens" });
      expect(r).toMatchObject({ text: "–", missing: true, value: null });
      expect(r.aria).toBe("토큰 수집 안 됨");
      expect(r.text).not.toContain("0");
    }
  });
  it("모르는 지표 이름도 값을 그대로 보인다(이름 하드코딩 없음)", () => {
    expect(formatMetric(obs(7), m, { name: "mystery" }).aria).toBe("mystery 7");
    expect(formatMetric(obs(7), m, { name: "mystery", kinds: { mystery: { kind: "tokenCount" } } }).aria).toBe("토큰 7");
  });
});

describe("metricPieces·sumMetrics·정렬", () => {
  it("우선 순서(횟수 → 오류 → 토큰 → 소요), 모르는 이름은 뒤", () => {
    const pieces = metricPieces({ zzz: obs(1), duration: obs(5), tokens: obs(2), count: obs(3), errors: obs(0) }, m);
    expect(pieces.map((p) => p.name)).toEqual(["count", "errors", "tokens", "duration", "zzz"]);
  });
  it("합계는 null을 0으로 더하지 않는다", () => {
    expect(sumMetrics([null, undefined])).toEqual({ total: null, complete: false });
    expect(sumMetrics([3, null, 4])).toEqual({ total: 7, complete: false });
    expect(sumMetrics([0, 0])).toEqual({ total: 0, complete: true });
  });
  it("정렬에서 null은 0이 아니라 맨 뒤", () => {
    const sorted = [5, null, 0, undefined, 2].sort(compareMetricValue);
    expect(sorted).toEqual([0, 2, 5, null, undefined]);
  });
  it("abbreviateNumber", () => {
    expect(abbreviateNumber(999)).toBe("999");
    expect(abbreviateNumber(41000)).toBe("41k");
  });
});

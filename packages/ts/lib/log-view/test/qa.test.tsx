import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { eventColumns, isErrorEvent, LogEventTable, PlaybackBar, sortEvents, splitSearchParams, buildFilterQuery, toTaxonomyView } from "../src";
import { events, slotFor, taxonomy } from "./fixtures";

afterEach(cleanup);

describe("QA 4R.16", () => {
  it("파일 여러 개: seq와 time 순서가 달라도 N번째는 (time,seq) 정렬 기준이고 aria 범위는 0~N", () => {
    // 파일 A: seq 1,2 (time 100,200), 파일 B: seq 3,4 (time 50,150)
    const evs = sortEvents([
      { seq: 1, time: 100 }, { seq: 2, time: 200 }, { seq: 3, time: 50 }, { seq: 4, time: 150 },
    ]);
    expect(evs.map((e) => e.seq)).toEqual([3, 1, 4, 2]);
    render(
      <PlaybackBar events={evs} index={2} onIndexChange={() => undefined} playing={false} onPlayingChange={() => undefined} speed={1} onSpeedChange={() => undefined} skipGaps onSkipGapsChange={() => undefined} describe={(i) => `seq${evs[i]?.seq}`} />,
    );
    const s = screen.getByRole("slider");
    expect(s.getAttribute("aria-valuemin")).toBe("0");
    expect(s.getAttribute("aria-valuemax")).toBe("4");
    expect(s.getAttribute("aria-valuenow")).toBe("3");
    expect(s.getAttribute("aria-valuetext")).toContain("3번째 / 4");
    expect(s.getAttribute("aria-valuetext")).toContain("seq4");
  });

  it("예약 파라미터는 서버 필터로 새지 않는다(실수로 필터에 들어 있어도)", () => {
    const { filter, screen: sc } = splitSearchParams("through=5&lane=a&view=x&range=1h&tab=raw&category=c1&category=c2");
    expect(Object.keys(filter)).toEqual(["category"]);
    expect(Object.keys(sc).sort()).toEqual(["lane", "range", "tab", "through", "view"]);
    expect(buildFilterQuery({ ...filter, through: "5", tab: "x" }).toString()).toBe("category=c1&category=c2");
  });

  it("오류 판정: status=failed·이름이 error여도 tone=danger가 아니면 오류 아님", () => {
    const v = toTaxonomyView({ categories: { error: { label: "error" }, ok: { tone: "danger" } } });
    expect(isErrorEvent({ category: "error" }, v)).toBe(false);
    expect(isErrorEvent({ category: "ok" }, v)).toBe(true);
  });

  it.each([10_000, 50_000])("%i행 LogEventTable 초기 렌더 시간(측정)", (n) => {
    const rows = events(n);
    const view = toTaxonomyView(taxonomy);
    const t0 = performance.now();
    const { container } = render(
      <LogEventTable rows={rows} columns={eventColumns(["time", "category", "title"])} taxonomy={view} isError={(r) => isErrorEvent(r, view)} slotFor={slotFor} height={480} />,
    );
    const ms = performance.now() - t0;
    console.log(`PERF rows=${n} render_ms=${ms.toFixed(1)} dom_rows=${container.querySelectorAll('[role="row"]').length}`);
    expect(container.querySelectorAll('[role="row"]').length).toBeLessThan(100);
    expect(ms).toBeLessThan(5000);
  });
});

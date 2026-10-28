import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { defaultFormatters } from "./format";
import { LogEventTable, eventColumns } from "./LogEventTable";
import { toTaxonomyView } from "./taxonomy";
import { formatEventTime, parseTimeMode, timeColumnWidth, type TimeMode } from "./timeMode";
import type { LogEventRow } from "./types";

// 2026-10-28T02:42:07Z. 시간대와 무관하게 검사하려고 기대값은 Date의 로컬 구성요소로 만든다.
const T = Date.UTC(2026, 9, 28, 2, 42, 7) / 1000;
const d = new Date(T * 1000);
const p2 = (n: number) => String(n).padStart(2, "0");
const wantDateTime = `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())} ${p2(d.getHours())}:${p2(d.getMinutes())}:${p2(d.getSeconds())}`;

describe("formatEventTime", () => {
  it("datetime: 날짜 포함 실제 시각, 툴팁에 ISO 원문과 시간대", () => {
    const r = formatEventTime("datetime", T, T - 5, defaultFormatters)!;
    expect(r.text).toBe(wantDateTime);
    expect(r.title).toContain("2026-10-28T02:42:07.000Z");
    expect(r.title).toContain(Intl.DateTimeFormat().resolvedOptions().timeZone);
  });
  it("time: 시각만", () => {
    expect(formatEventTime("time", T, null, defaultFormatters)!.text).toBe(wantDateTime.slice(11) + ".000");
  });
  it("elapsed: 기준 시각에서 지난 시간", () => {
    expect(formatEventTime("elapsed", T, T - 83.5, defaultFormatters)!.text).toBe("+1:23.500");
  });
  it("기록된 시각이 없으면 null이고, 경과 시각으로 대신하지 않는다", () => {
    expect(formatEventTime("datetime", null, T, defaultFormatters)).toBeNull();
    expect(formatEventTime("elapsed", undefined, T, defaultFormatters)).toBeNull();
    expect(formatEventTime("elapsed", T, null, defaultFormatters)).toBeNull();
  });
  it("모르는 값은 기본값, 열 폭은 방식에 맞춘다", () => {
    expect(parseTimeMode("nope")).toBe("datetime");
    expect(parseTimeMode(null, "elapsed")).toBe("elapsed");
    expect(timeColumnWidth("datetime")).toBeGreaterThan(timeColumnWidth("time"));
  });
});

const row = (uid: string, time: number | null): LogEventRow => ({ uid, seq: 1, time, category: "x", title: uid } as unknown as LogEventRow);
const common = { taxonomy: toTaxonomyView(null), isError: () => false, slotFor: () => 0, height: 200 };

function Harness({ rows, origin, onChange }: { rows: LogEventRow[]; origin: number | null; onChange?: (m: TimeMode) => void }) {
  const [mode, setMode] = useState<TimeMode>("datetime");
  return <LogEventTable {...common} rows={rows} columns={eventColumns(["time", "title"], undefined, { time: timeColumnWidth(mode) })} timeMode={mode} onTimeModeChange={(m) => { setMode(m); onChange?.(m); }} originTime={origin} />;
}

afterEach(cleanup);

describe("LogEventTable 시각 열", () => {
  it("기본은 날짜 포함 실제 시각이고, 머리 메뉴로 방식을 바꾼다", () => {
    const onChange = vi.fn();
    render(<Harness rows={[row("a", T)]} origin={T - 60} onChange={onChange} />);
    expect(screen.getByText(wantDateTime)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /시각 표시 방식/ }));
    const items = screen.getAllByRole("menuitemradio");
    expect(items.map((i) => i.getAttribute("aria-checked"))).toEqual(["true", "false", "false"]);
    fireEvent.click(items[2]!);
    expect(onChange).toHaveBeenCalledWith("elapsed");
    expect(screen.getByText("+1:00.000")).toBeTruthy();
    expect(screen.queryByRole("menu")).toBeNull();
  });
  it("시각이 기록되지 않은 행은 어느 방식에서도 대시를 보인다", () => {
    render(<Harness rows={[row("a", null)]} origin={T} />);
    const cells = screen.getAllByRole("gridcell");
    expect(cells[0]!.textContent).toBe("–");
    fireEvent.click(screen.getByRole("button", { name: /시각 표시 방식/ }));
    fireEvent.click(screen.getAllByRole("menuitemradio")[2]!);
    expect(screen.getAllByRole("gridcell")[0]!.textContent).toBe("–");
  });
  it("Esc로 메뉴를 닫는다", () => {
    render(<Harness rows={[row("a", T)]} origin={T} />);
    fireEvent.click(screen.getByRole("button", { name: /시각 표시 방식/ }));
    fireEvent.keyDown(screen.getAllByRole("menuitemradio")[0]!, { key: "Escape" });
    expect(screen.queryByRole("menu")).toBeNull();
  });
});

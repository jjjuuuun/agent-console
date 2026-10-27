import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { LogEventTable, eventColumns } from "./LogEventTable";
import { toTaxonomyView } from "./taxonomy";

afterEach(cleanup);

const common = { columns: eventColumns(["time", "category"]), taxonomy: toTaxonomyView(null), isError: () => false, slotFor: () => 0 };

describe("LogEventTable 빈 표", () => {
  it("기본은 비었다는 안내가 표를 대신한다", () => {
    render(<LogEventTable rows={[]} {...common} renderEmpty={() => <p>비었음</p>} />);
    expect(screen.getByText("비었음")).toBeTruthy();
    expect(screen.queryAllByRole("columnheader")).toHaveLength(0);
  });
  it("emptyBelowHeader면 표 머리를 그리고 안내를 그 아래에 놓는다", () => {
    render(<LogEventTable rows={[]} {...common} emptyBelowHeader renderEmpty={() => <p>비었음</p>} />);
    const heads = screen.getAllByRole("columnheader");
    expect(heads).toHaveLength(2);
    const note = screen.getByText("비었음");
    expect(heads[0]!.compareDocumentPosition(note) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
  it("불러오는 중에는 emptyBelowHeader여도 스켈레톤이 표를 대신한다", () => {
    render(<LogEventTable rows={[]} {...common} loading emptyBelowHeader renderEmpty={() => <p>비었음</p>} />);
    expect(screen.queryByText("비었음")).toBeNull();
  });
});

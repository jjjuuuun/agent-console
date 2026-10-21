import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it } from "vitest";
import { buildBreadcrumb, openedFromState, parentState, readOpenedFrom } from "./openedFrom";
import { TeamBreadcrumb } from "./TeamBreadcrumb";

afterEach(cleanup);

describe("openedFrom 라우터 상태", () => {
  it("모양이 맞을 때만 읽는다(직접 입력·새로고침이면 없다)", () => {
    expect(readOpenedFrom(undefined)).toBeUndefined();
    expect(readOpenedFrom({ openedFrom: { id: "a" } })).toBeUndefined();
    expect(readOpenedFrom({ openedFrom: { definitionKind: "k", id: "a", title: "가" } })).toEqual({ definitionKind: "k", id: "a", title: "가" });
  });
  it("자식을 열 때 지금 화면이 부모가 되고 지금 화면의 부모는 trail로 이어진다", () => {
    const first = openedFromState({ definitionKind: "k", id: "root", title: "루트" }, undefined);
    expect(first.openedFrom).toEqual({ definitionKind: "k", id: "root", title: "루트" });
    const second = openedFromState({ definitionKind: "k", id: "mid", title: "중간" }, first.openedFrom);
    expect(second.openedFrom.trail).toEqual([{ id: "root", title: "루트" }]);
  });
  it("부모로 돌아가면 부모 자신의 openedFrom(trail의 마지막)을 되살리고, 더 위가 없으면 상태가 없다", () => {
    expect(parentState({ definitionKind: "k", id: "root", title: "루트" })).toBeUndefined();
    expect(parentState({ definitionKind: "k", id: "mid", title: "중간", trail: [{ id: "root", title: "루트" }] })).toEqual({ openedFrom: { definitionKind: "k", id: "root", title: "루트" } });
    expect(parentState({ definitionKind: "k", id: "c", title: "다", trail: [{ id: "a", title: "가" }, { id: "b", title: "나" }] })?.openedFrom).toEqual({ definitionKind: "k", id: "b", title: "나", trail: [{ id: "a", title: "가" }] });
  });
});

describe("브레드크럼", () => {
  const from = { definitionKind: "k", id: "p4", title: "넷", trail: [{ id: "p1", title: "하나" }, { id: "p2", title: "둘" }, { id: "p3", title: "셋" }] };
  it("가까운 3단계만 보이고 앞쪽은 … 로 접으며 마지막이 현재 화면이다", () => {
    const { crumbs, hidden } = buildBreadcrumb({ root: { label: "팀 구성", href: "/teams" }, from, current: "현재", hrefOf: (id) => `/teams/${id}` });
    expect(crumbs.map((c) => c.label)).toEqual(["팀 구성", "…", "둘", "셋", "넷", "현재"]);
    expect(hidden).toEqual(["하나"]);
  });
  it("부모 항목 링크는 그 부모 화면이 받을 상태를 싣는다", () => {
    const { crumbs } = buildBreadcrumb({ root: { label: "팀 구성" }, from, current: "현재", hrefOf: (id) => `/teams/${id}` });
    const three = crumbs.find((c) => c.label === "셋")!;
    expect(three.state?.openedFrom).toMatchObject({ id: "p2", title: "둘", trail: [{ id: "p1", title: "하나" }] });
    expect(crumbs.find((c) => c.label === "둘")?.state?.openedFrom).toMatchObject({ id: "p1" });
  });
  it("컴포넌트: 링크와 현재 위치(aria-current)", () => {
    render(
      <MemoryRouter>
        <TeamBreadcrumb rootLabel="팀 구성" rootHref="/teams" from={{ definitionKind: "k", id: "p", title: "개발 팀" }} current="검토 파이프라인" hrefOf={(id) => `/teams/${id}`} />
      </MemoryRouter>,
    );
    const nav = screen.getByRole("navigation", { name: "위치" });
    expect(within(nav).getByRole("link", { name: "팀 구성" }).getAttribute("href")).toBe("/teams");
    expect(within(nav).getByRole("link", { name: "개발 팀" }).getAttribute("href")).toBe("/teams/p");
    expect(nav.querySelector("[aria-current='page']")?.textContent).toBe("검토 파이프라인");
  });
});

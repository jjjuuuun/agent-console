import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FolderBrowser } from "./FolderBrowser";
import { createTranslate } from "./messages";
import type { FolderListFn, FolderListingData } from "./types";

afterEach(cleanup);

const t = createTranslate();
const parentOf = (p: string) => (p === "" ? null : p.includes("/") ? p.slice(0, p.lastIndexOf("/")) : "");
/** 상대 경로 트리(루트 = 빈 문자열). 폴더 이름은 데이터다. */
const TREE: Record<string, string[]> = { "": ["alpha", "beta"], alpha: ["inner"], "alpha/inner": [], beta: [] };
const list: FolderListFn = async ({ path }) =>
  ({ path, parent: parentOf(path), entries: (TREE[path] ?? []).map((name) => ({ name, path: path === "" ? name : `${path}/${name}` })) }) satisfies FolderListingData;

const settle = () => act(async () => { await Promise.resolve(); });
const list_ = () => screen.getByRole("listbox", { hidden: true });

describe("FolderBrowser rootPath", () => {
  it("빈 문자열 루트에서 시작하고 목록·빵부스러기 첫 조각이 루트다", async () => {
    render(<FolderBrowser id="b" t={t} roots={[]} startPath={null} list={list} rootPath="" rootLabel="프로젝트" />);
    await settle();
    expect(screen.getByRole("option", { name: /alpha/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: "프로젝트" })).toBeTruthy();
  });

  it("루트에서 위로 가도(←) 시작 위치 목록으로 나가지 않는다", async () => {
    const onNavigate = vi.fn();
    render(<FolderBrowser id="b" t={t} roots={[]} startPath={null} list={list} rootPath="" onNavigate={onNavigate} />);
    await settle();
    fireEvent.keyDown(list_(), { key: "ArrowLeft" });
    await settle();
    expect(screen.getByRole("option", { name: /alpha/ })).toBeTruthy();
    expect(onNavigate).not.toHaveBeenCalled();
  });

  it("하위로 들어가면 빵부스러기가 루트 아래만 보이고, 위로 가면 루트에서 멈춘다", async () => {
    const onNavigate = vi.fn();
    render(<FolderBrowser id="b" t={t} roots={[]} startPath={null} list={list} rootPath="" rootLabel="프로젝트" onNavigate={onNavigate} />);
    await settle();
    fireEvent.keyDown(list_(), { key: "Enter" });
    await settle();
    expect(onNavigate).toHaveBeenLastCalledWith("alpha");
    expect(screen.getByRole("option", { name: /inner/ })).toBeTruthy();
    fireEvent.keyDown(list_(), { key: "ArrowLeft" });
    await settle();
    expect(onNavigate).toHaveBeenLastCalledWith("");
    fireEvent.keyDown(list_(), { key: "ArrowLeft" });
    await settle();
    expect(onNavigate).toHaveBeenCalledTimes(2);
  });

  it("루트 밖 시작 위치는 루트로 당긴다", async () => {
    render(<FolderBrowser id="b" t={t} roots={[]} startPath="/etc" list={list} rootPath="alpha" />);
    await settle();
    expect(screen.getByRole("option", { name: /inner/ })).toBeTruthy();
  });

  it("루트가 하위 폴더여도 그 위로 올라가지 않는다", async () => {
    const onNavigate = vi.fn();
    render(<FolderBrowser id="b" t={t} roots={[]} startPath="alpha/inner" list={list} rootPath="alpha" onNavigate={onNavigate} />);
    await settle();
    fireEvent.keyDown(list_(), { key: "ArrowLeft" });
    await settle();
    expect(onNavigate).toHaveBeenLastCalledWith("alpha");
    fireEvent.keyDown(list_(), { key: "ArrowLeft" });
    await settle();
    expect(onNavigate).toHaveBeenCalledTimes(1);
  });

  it("showHiddenToggle=false면 숨김 토글을 그리지 않는다", async () => {
    render(<FolderBrowser id="b" t={t} roots={[]} startPath={null} list={list} rootPath="" showHiddenToggle={false} />);
    await settle();
    expect(screen.queryByRole("checkbox")).toBeNull();
  });
});

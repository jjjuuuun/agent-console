import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { FolderCheck } from "@agent-console/contracts/projects";
import { folderCheckOutcome } from "@agent-console/projects";
import { ApiError } from "@agent-console/api-client";
import { ProjectFolderDialog, type FolderSubmit, type ProjectFolderDialogProps } from "./ProjectFolderDialog";
import type { FolderApi } from "./useFolderApi";
import { canSubmitAdd, canSubmitRepath, folderBaseName, suggestionFor } from "./projectFolderLib";
import { IDLE_STATE } from "@agent-console/folder-picker";

const fc = (path: string, over: Partial<FolderCheck> = {}): FolderCheck => ({
  input: path,
  path,
  exists: true,
  is_dir: true,
  readable: true,
  writable: true,
  can_create: false,
  status: "ok",
  suggested_id: "payments",
  config_dir: ".cfg-dir",
  ...over,
});

/** 가짜 폴더 API: 경로마다 확인 응답을 정한다. */
function fakeApi(checks: Record<string, FolderCheck>, over: Partial<FolderApi> = {}): FolderApi {
  const seen = new Map<string, FolderCheck>();
  return {
    check: vi.fn(async (r) => {
      const c = checks[r.path] ?? fc(r.path);
      seen.set(c.input, c);
      if (c.path != null) seen.set(c.path, c);
      return folderCheckOutcome(c, { projectName: (id) => `이름-${id}` });
    }),
    list: vi.fn(async (r) => ({ path: r.path, parent: null, entries: [{ name: "alpha", path: `${r.path}/alpha` }] })),
    createFolder: vi.fn(async () => ({ ok: false as const, code: "x" })),
    pickNative: undefined,
    capabilities: { browse: true, native_dialog: false },
    roots: [{ kind: "home", path: "/home/me", label: "홈" }],
    lastCheckFor: (p) => (p === null ? undefined : seen.get(p)),
    configDir: ".cfg-dir",
    ...over,
  };
}

function setup(over: Partial<ProjectFolderDialogProps> & { checks?: Record<string, FolderCheck> } = {}) {
  const onSubmit = vi.fn<(v: FolderSubmit) => Promise<void>>(async () => undefined);
  const onClose = vi.fn();
  const { checks = {}, ...rest } = over;
  const api = fakeApi(checks);
  render(<ProjectFolderDialog mode="add" api={api} onSubmit={onSubmit} onClose={onClose} {...rest} />);
  return { onSubmit, onClose, api };
}

/** 직접 입력을 열어 경로를 넣고 확인(300ms 디바운스 없이 붙여넣기처럼 blur로 즉시)을 끝낸다. */
async function typePath(path: string) {
  if (screen.queryByLabelText("폴더 경로") === null) fireEvent.click(screen.getByRole("button", { name: "경로를 직접 입력" }));
  const input = screen.getByLabelText("폴더 경로");
  fireEvent.change(input, { target: { value: path } });
  fireEvent.blur(input);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
}

beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("projectFolderLib", () => {
  it("폴더 이름은 마지막 조각(구분자 / 와 \\ 모두), 루트·드라이브면 빈 문자열", () => {
    expect(folderBaseName("/home/me/work/payments")).toBe("payments");
    expect(folderBaseName("C:\\Users\\me\\앱 폴더\\")).toBe("앱 폴더");
    expect(folderBaseName("/")).toBe("");
    expect(folderBaseName("C:")).toBe("");
  });
  it("제안: 기존 구성이 읽히면 그 이름·설명, 깨졌으면 폴더 이름, id는 서버 값 그대로", () => {
    const state = { ...IDLE_STATE, forInput: "/w/app", check: { input: "/w/app", path: "/w/app", exists: true, is_dir: true, readable: true, writable: true, can_create: false } };
    const found = suggestionFor(state, fc("/w/app", { suggested_id: "app-2", existing: { state: "found", name: "기존 이름", description: "설명", definitions: 3 } }));
    expect(found).toMatchObject({ name: "기존 이름", id: "app-2", description: "설명", adopted: { name: "기존 이름", definitions: 3 }, manifestInvalid: false });
    const bad = suggestionFor(state, fc("/w/app", { existing: { state: "invalid", name: "믿지 않음" } }));
    expect(bad).toMatchObject({ name: "app", adopted: null, manifestInvalid: true });
  });
  it("제출 가능 조건", () => {
    const ok = { ...IDLE_STATE, submittable: true };
    expect(canSubmitAdd(ok, "이름", false, false)).toBe(true);
    expect(canSubmitAdd(ok, " ", false, false)).toBe(false);
    expect(canSubmitAdd(ok, "이름", true, false)).toBe(false);
    expect(canSubmitAdd(ok, "이름", false, true)).toBe(false);
    expect(canSubmitAdd({ ...ok, reregister: true }, "", false, false)).toBe(true);
    expect(canSubmitRepath({ ...ok, reregister: true }, false, false)).toBe(false);
    expect(canSubmitRepath(IDLE_STATE, false, false)).toBe(false);
  });
});

describe("ProjectFolderDialog add", () => {
  it("첫 포커스는 [폴더 선택…], 직접 입력은 접혀 있고, 선택 전엔 추가가 aria-disabled", () => {
    setup();
    const dlg = screen.getByRole("dialog", { name: "프로젝트 폴더 추가" });
    expect(document.activeElement).toBe(within(dlg).getByRole("button", { name: "폴더 선택…" }));
    expect(within(dlg).queryByLabelText("폴더 경로")).toBeNull();
    expect(within(dlg).getByRole("button", { name: "프로젝트 추가" }).getAttribute("aria-disabled")).toBe("true");
    // 선택 전에도 "{dir} 폴더를 만듭니다" 줄이 보인다(마지막으로 안 확인 dir 대신 api.configDir)
    expect(dlg.textContent).toContain(".cfg-dir");
  });

  it("경로를 확인하면 이름은 폴더 이름, id는 서버 제안으로 채워지고 제출 값에 실린다", async () => {
    const { onSubmit } = setup();
    await typePath("/home/me/work/payments");
    await waitFor(() => expect((screen.getByLabelText(/^이름/) as HTMLInputElement).value).toBe("payments"));
    const add = screen.getByRole("button", { name: "프로젝트 추가" });
    expect(add.getAttribute("aria-disabled")).toBeNull();
    fireEvent.click(screen.getByText("고급 (id · 설명)"));
    expect((screen.getByLabelText("id") as HTMLInputElement).value).toBe("payments");
    await act(async () => {
      fireEvent.click(add);
    });
    expect(onSubmit).toHaveBeenCalledWith({ kind: "add", folder: "/home/me/work/payments", name: "payments", id: "payments", description: undefined, adopted: null, manifestInvalid: false });
  });

  it("직접 고친 이름은 다른 폴더를 골라도 덮어쓰지 않는다", async () => {
    setup();
    await typePath("/w/a");
    await waitFor(() => expect((screen.getByLabelText(/^이름/) as HTMLInputElement).value).toBe("a"));
    fireEvent.change(screen.getByLabelText(/^이름/), { target: { value: "내 이름" } });
    const input = screen.getByLabelText("폴더 경로");
    fireEvent.change(input, { target: { value: "/w/b" } });
    fireEvent.blur(input);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect((screen.getByLabelText(/^이름/) as HTMLInputElement).value).toBe("내 이름");
  });

  it("기존 구성이 있는 폴더는 그 이름·개수로 안내하고 채택 개수를 넘긴다", async () => {
    const { onSubmit } = setup({ checks: { "/w/app": fc("/w/app", { existing: { state: "found", name: "기존 앱", definitions: 3 }, suggested_id: "app-2" }) } });
    await typePath("/w/app");
    await waitFor(() => expect((screen.getByLabelText(/^이름/) as HTMLInputElement).value).toBe("기존 앱"));
    expect(document.body.textContent).toContain("구성 3개");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "프로젝트 추가" }));
    });
    expect(onSubmit.mock.calls[0]?.[0]).toMatchObject({ kind: "add", name: "기존 앱", id: "app-2", adopted: 3 });
  });

  it("설정 파일이 깨진 폴더도 추가할 수 있다(폴더에 쓰지 않는다는 안내)", async () => {
    const { onSubmit } = setup({ checks: { "/w/bad": fc("/w/bad", { existing: { state: "invalid", issue: undefined } }) } });
    await typePath("/w/bad");
    await waitFor(() => expect(document.body.textContent).toContain("프로젝트 설정 파일을 읽을 수 없습니다"));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "프로젝트 추가" }));
    });
    expect(onSubmit.mock.calls[0]?.[0]).toMatchObject({ kind: "add", manifestInvalid: true });
  });

  it("보관된 같은 폴더는 [다시 등록]으로 같은 프로젝트를 되살린다", async () => {
    const { onSubmit } = setup({ checks: { "/w/old": fc("/w/old", { status: "taken_archived", conflict: { project_id: "old-id", relation: "same", archived: true } }) } });
    await typePath("/w/old");
    const again = await screen.findByRole("button", { name: "다시 등록" });
    expect(again.getAttribute("aria-disabled")).toBeNull();
    await act(async () => {
      fireEvent.click(again);
    });
    expect(onSubmit).toHaveBeenCalledWith({ kind: "reregister", projectId: "old-id", name: "이름-old-id" });
  });

  it("이미 등록된 폴더는 추가가 막힌다", async () => {
    const { onSubmit } = setup({ checks: { "/w/taken": fc("/w/taken", { status: "taken", conflict: { project_id: "p1", relation: "same" } }) } });
    await typePath("/w/taken");
    await waitFor(() => expect(document.body.textContent).toContain("이미 ‘이름-p1’ 프로젝트로 등록된 폴더입니다"));
    fireEvent.click(screen.getByRole("button", { name: "프로젝트 추가" }));
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("제출이 409(보관된 폴더)로 거절되면 안에서 [다시 등록]을 안내한다", async () => {
    const { onSubmit } = setup();
    onSubmit.mockRejectedValueOnce(new ApiError(409, { code: "project.folder_taken", message: "m", details: { project_id: "old", archived: true } }));
    await typePath("/w/x");
    await waitFor(() => expect((screen.getByLabelText(/^이름/) as HTMLInputElement).value).toBe("x"));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "프로젝트 추가" }));
    });
    expect(await screen.findByText(/등록했다가 해제한 폴더입니다/)).toBeTruthy();
    await act(async () => {
      fireEvent.click(screen.getAllByRole("button", { name: "다시 등록" })[0]!);
    });
    expect(onSubmit).toHaveBeenLastCalledWith({ kind: "reregister", projectId: "old", name: "old" });
  });

  it("서버 오류는 대화상자 안 배너로 보이고 닫히지 않는다", async () => {
    const { onSubmit, onClose } = setup();
    onSubmit.mockRejectedValueOnce(new ApiError(500, { code: "x", message: "서버가 거절했습니다" }));
    await typePath("/w/x");
    await waitFor(() => expect((screen.getByLabelText(/^이름/) as HTMLInputElement).value).toBe("x"));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "프로젝트 추가" }));
    });
    expect(await screen.findByText("서버가 거절했습니다")).toBeTruthy();
    expect(onClose).not.toHaveBeenCalled();
  });

  it("앱 안 찾아보기: native_dialog=false면 [폴더 선택…]이 패널을 열고, 폴더를 고르면 곧바로 확인된다", async () => {
    const { api } = setup();
    fireEvent.click(screen.getByRole("button", { name: "폴더 선택…" }));
    const list = await screen.findByRole("listbox", { name: "폴더 목록" });
    fireEvent.doubleClick(await within(list).findByRole("option", { name: /홈/ }));
    await waitFor(() => expect(api.list).toHaveBeenCalledWith(expect.objectContaining({ path: "/home/me" }), expect.anything()));
    fireEvent.doubleClick(await within(screen.getByRole("listbox", { name: "폴더 목록" })).findByRole("option", { name: /alpha/ }));
    await waitFor(() => expect(api.check).toHaveBeenCalledWith(expect.objectContaining({ path: "/home/me/alpha" }), expect.anything()));
  });

  it("Esc는 대화상자를 닫는다(대기·패널이 없을 때)", () => {
    const { onClose } = setup();
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
});

describe("ProjectFolderDialog repath", () => {
  const target = { id: "p1", name: "결제", folder: "/old/place", statusLabel: "폴더 없음", configDir: ".cfg-dir" };

  it("제목·이전 경로·상태 칩·안내가 보이고 이름/id 칸은 없다. 확인 요청에 자기 id를 제외로 싣는다", async () => {
    const { api } = setup({ mode: "repath", target });
    const dlg = screen.getByRole("dialog", { name: "경로 다시 지정 — 결제" });
    expect(dlg.textContent).toContain("/old/place");
    expect(dlg.textContent).toContain("폴더 없음");
    expect(dlg.textContent).toContain("함께 옮겼는지 확인하세요");
    expect(dlg.textContent).not.toContain("로그인");
    expect(within(dlg).queryByLabelText(/^이름/)).toBeNull();
    await typePath("/new/place");
    await waitFor(() => expect(api.check).toHaveBeenCalled());
    expect(vi.mocked(api.check).mock.calls.at(-1)?.[0]).toMatchObject({ path: "/new/place", excludeProjectId: "p1" });
  });

  it("제출은 새 경로를 보내고, 같은 경로면 제출이 막힌다", async () => {
    const { onSubmit } = setup({ mode: "repath", target });
    await typePath("/old/place");
    await waitFor(() => expect(document.body.textContent).toContain("이전 경로와 같습니다"));
    fireEvent.click(screen.getByRole("button", { name: "경로 바꾸기" }));
    expect(onSubmit).not.toHaveBeenCalled();
    await typePath("/new/place");
    await waitFor(() => expect(screen.getByRole("button", { name: "경로 바꾸기" }).getAttribute("aria-disabled")).toBeNull());
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "경로 바꾸기" }));
    });
    expect(onSubmit).toHaveBeenCalledWith({ kind: "repath", folder: "/new/place" });
  });

  it("폴더 미지정 프로젝트는 제목이 '폴더 지정'이고 제안 경로를 [이 경로 사용]으로 채운다", async () => {
    setup({ mode: "repath", target: { ...target, folder: null, suggestedFolder: "/suggest/here" } });
    expect(screen.getByRole("dialog", { name: "폴더 지정 — 결제" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "이 경로 사용" }));
    await waitFor(() => expect(document.body.textContent).toContain("/suggest/here"));
  });
});

import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ShortcutProvider, computeEffectiveKeys, type ShortcutDef } from "@agent-console/ui";
import { DEFAULT_ROUTES, gotoShortcuts } from "../../shell/routeConfig";
import { PROJECT_SHORTCUT_DEFS } from "../projects";
import { DOC_SHORTCUT_DEFS, DOC_SHORTCUT_SCOPE, buildDocShortcuts, useDocShortcuts, type DocShortcutAction } from "./docShortcuts";
import { TASK_SHORTCUT_DEFS, TASK_SHORTCUT_SCOPE } from "./taskShortcuts";

afterEach(cleanup);

const SHELL_FIXED: Omit<ShortcutDef, "run">[] = [
  { id: "palette.open", scope: "global", keys: "Mod+K", titleKey: "x", modifierRequired: true },
  { id: "pending.jump", scope: "global", keys: "Alt+J", titleKey: "x", modifierRequired: true },
  { id: "sidebar.toggle", scope: "global", keys: "Mod+Shift+B", titleKey: "x", modifierRequired: true },
  { id: "help.open", scope: "global", keys: "?", titleKey: "x" },
];

function Inner({ handlers }: { handlers: Partial<Record<DocShortcutAction, () => void>> }) {
  useDocShortcuts(handlers);
  return <textarea aria-label="편집기" data-ac-editable="" />;
}

function Host({ handlers, overrides }: { handlers: Partial<Record<DocShortcutAction, () => void>>; overrides?: Record<string, string> }) {
  return (
    <ShortcutProvider defaults={[]} {...(overrides ? { overrides } : {})} onWarn={null}>
      <Inner handlers={handlers} />
    </ShortcutProvider>
  );
}

describe("문서 탭 단축키 데이터", () => {
  it("명세 키(Alt+E/P/B, Ctrl+Alt+↑↓)와 줄 이동이 표에 있다", () => {
    expect(Object.fromEntries(DOC_SHORTCUT_DEFS.map((d) => [d.action, d.keys]))).toEqual({
      modeEdit: "Alt+E",
      modePreview: "Alt+P",
      modeSplit: "Alt+B",
      prevDoc: "Ctrl+Alt+ArrowUp",
      nextDoc: "Ctrl+Alt+ArrowDown",
      gotoLine: "Ctrl+G",
    });
  });

  it("셸 전역 키·g 이동 키·프로젝트 키·작업 탭 키와 겹치지 않는다(충돌 검사)", () => {
    const goto = gotoShortcuts(DEFAULT_ROUTES, () => {});
    const defs = [
      ...SHELL_FIXED,
      ...goto.map((d) => ({ id: d.id, scope: d.scope, keys: d.keys, titleKey: d.titleKey })),
      ...PROJECT_SHORTCUT_DEFS.map((d) => ({ ...d, scope: "global", modifierRequired: true })),
      ...TASK_SHORTCUT_DEFS.map((d) => ({ id: d.id, scope: TASK_SHORTCUT_SCOPE, keys: d.keys, titleKey: d.titleKey })),
      ...DOC_SHORTCUT_DEFS.map((d) => ({ id: d.id, scope: DOC_SHORTCUT_SCOPE, keys: d.keys, titleKey: d.titleKey, modifierRequired: true })),
    ];
    expect(computeEffectiveKeys(defs, {}, "other").filter((e) => e.conflict !== undefined)).toEqual([]);
  });

  it("설정이 같은 범위의 다른 동작과 같은 키를 주면 충돌로 드러난다", () => {
    const defs = DOC_SHORTCUT_DEFS.map((d) => ({ id: d.id, scope: DOC_SHORTCUT_SCOPE, keys: d.keys, titleKey: d.titleKey }));
    const effective = computeEffectiveKeys(defs, { "specs.doc.mode.split": "Alt+E" }, "other");
    expect(effective.find((e) => e.id === "specs.doc.mode.edit")?.conflict).toBe("specs.doc.mode.split");
  });

  it("핸들러가 있는 동작만 등록한다", () => {
    expect(buildDocShortcuts({ modeEdit: () => {} }).map((d) => d.id)).toEqual(["specs.doc.mode.edit"]);
  });
});

describe("문서 탭 단축키 동작", () => {
  it("편집기에 포커스가 있어도 수식키 조합은 동작한다", () => {
    const h = { modeEdit: vi.fn(), modePreview: vi.fn(), modeSplit: vi.fn(), prevDoc: vi.fn(), nextDoc: vi.fn(), gotoLine: vi.fn() };
    const { getByLabelText } = render(<Host handlers={h} />);
    const editor = getByLabelText("편집기");
    fireEvent.keyDown(editor, { key: "e", altKey: true });
    fireEvent.keyDown(editor, { key: "p", altKey: true });
    fireEvent.keyDown(editor, { key: "b", altKey: true });
    fireEvent.keyDown(editor, { key: "ArrowUp", ctrlKey: true, altKey: true });
    fireEvent.keyDown(editor, { key: "ArrowDown", ctrlKey: true, altKey: true });
    fireEvent.keyDown(editor, { key: "g", ctrlKey: true });
    for (const fn of Object.values(h)) expect(fn).toHaveBeenCalledTimes(1);
  });

  it("IME 조합 중에는 무시한다", () => {
    const modeEdit = vi.fn();
    const { getByLabelText } = render(<Host handlers={{ modeEdit }} />);
    fireEvent.keyDown(getByLabelText("편집기"), { key: "e", altKey: true, isComposing: true });
    fireEvent.keyDown(getByLabelText("편집기"), { key: "Process", keyCode: 229, altKey: true });
    expect(modeEdit).not.toHaveBeenCalled();
  });

  it("ui.keybindings로 키를 바꾸면 새 키로 동작하고 옛 키는 동작하지 않는다", () => {
    const modeEdit = vi.fn();
    const { getByLabelText } = render(<Host handlers={{ modeEdit }} overrides={{ "specs.doc.mode.edit": "Alt+1" }} />);
    fireEvent.keyDown(getByLabelText("편집기"), { key: "e", altKey: true });
    expect(modeEdit).not.toHaveBeenCalled();
    fireEvent.keyDown(getByLabelText("편집기"), { key: "1", altKey: true });
    expect(modeEdit).toHaveBeenCalledTimes(1);
  });
});

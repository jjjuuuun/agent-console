import { cleanup, fireEvent, screen } from "@testing-library/react";
import { render } from "../../testing/i18nRender";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { StorageProvider } from "../../app/StorageContext";
import { createSafeStorage } from "../../app/storage";
import { PROJECT_REGION_COLLAPSED_KEY, SidebarProjectRegion } from "./SidebarProjectRegion";
import type { ProjectsValue } from "./ProjectsContext";

const projects = vi.hoisted(() => ({ value: undefined as unknown as ProjectsValue }));
vi.mock("./ProjectsContext", () => ({ useProjects: () => projects.value }));

afterEach(cleanup);

function fakeProjects(): ProjectsValue {
  return {
    enabled: true,
    loading: false,
    views: [],
    current: null,
    switcherOpen: false,
    setSwitcherOpen: () => {},
    openHome: () => {},
    requestAddFolder: () => {},
    requestRepath: () => {},
    requestUnregister: () => {},
  } as unknown as ProjectsValue;
}

function memoryBacking(): Storage {
  const map = new Map<string, string>();
  return {
    get length() {
      return map.size;
    },
    key: (i: number) => Array.from(map.keys())[i] ?? null,
    getItem: (k: string) => map.get(k) ?? null,
    setItem: (k: string, v: string) => void map.set(k, v),
    removeItem: (k: string) => void map.delete(k),
    clear: () => map.clear(),
  };
}

function mount(storage: ReturnType<typeof createSafeStorage>) {
  projects.value = fakeProjects();
  return render(
    <MemoryRouter>
      <StorageProvider storage={storage}>
        <SidebarProjectRegion rail={false} />
      </StorageProvider>
    </MemoryRouter>,
  );
}

const toggle = (expanded: boolean) => screen.getByRole("button", { name: /프로젝트/, expanded });

describe("SidebarProjectRegion 접힘 기억 (R15.8)", () => {
  it("접은 뒤 언마운트했다 다시 마운트해도 접힘이 유지된다", () => {
    const storage = createSafeStorage(memoryBacking());
    const first = mount(storage);
    fireEvent.click(toggle(true));
    expect(storage.get(PROJECT_REGION_COLLAPSED_KEY)).toBe("1");
    expect(screen.queryByRole("list", { name: "프로젝트 목록" })).toBeNull();
    first.unmount();

    mount(storage);
    expect(toggle(false)).toBeTruthy();
    expect(screen.queryByRole("list", { name: "프로젝트 목록" })).toBeNull();

    fireEvent.click(toggle(false));
    expect(storage.get(PROJECT_REGION_COLLAPSED_KEY)).toBe("0");
  });

  it("새로고침: 같은 바탕 저장소 위에 createSafeStorage를 새로 만들어도 접힘이 유지된다", () => {
    const backing = memoryBacking();
    const first = mount(createSafeStorage(backing));
    fireEvent.click(toggle(true));
    first.unmount();

    const reloaded = createSafeStorage(backing);
    expect(reloaded.get(PROJECT_REGION_COLLAPSED_KEY)).toBe("1");
    mount(reloaded);
    expect(toggle(false)).toBeTruthy();
    expect(screen.queryByRole("list", { name: "프로젝트 목록" })).toBeNull();
  });

  it("저장소 접근이 throw해도 기본 펼침으로 동작하고 접기는 이번 마운트에서 된다", () => {
    const boom = (): never => {
      throw new Error("denied");
    };
    const broken = createSafeStorage({ getItem: boom, setItem: boom, removeItem: boom, key: boom, clear: boom, length: 0 } as unknown as Storage);
    mount(broken);
    expect(toggle(true)).toBeTruthy();
    fireEvent.click(toggle(true));
    expect(toggle(false)).toBeTruthy();
  });
});

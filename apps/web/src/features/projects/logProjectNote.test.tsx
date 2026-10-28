import { act, cleanup, render, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { useEffect, useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Project } from "@agent-console/contracts/projects";
import { createSafeStorage } from "../../app/storage";
import { StorageProvider } from "../../app/StorageContext";
import { LogProjectNote } from "./AccountAndLogs";

afterEach(cleanup);

// 프로젝트 문맥만 바꿔 끼운다(목록 로드 시점을 정확히 조절하려고).
type Mock = { enabled: boolean; current: string | null; currentProject: Project | undefined };
let state: Mock = { enabled: true, current: null, currentProject: undefined };
const listeners = new Set<() => void>();
const setState = (next: Mock) => {
  state = next;
  listeners.forEach((l) => l());
};
vi.mock("./ProjectsContext", () => ({
  useProjects: () => {
    const [, force] = useState(0);
    useEffect(() => {
      const l = () => force((n) => n + 1);
      listeners.add(l);
      return () => void listeners.delete(l);
    }, []);
    return state;
  },
}));

const project = (id: string, over: Partial<Project> = {}) => ({ id, name: id.toUpperCase(), ...over }) as Project;

describe("LogProjectNote: 프로젝트 교체 시 로그 필터", () => {
  it("목록이 늦게 로드돼도(첫 렌더 wanted 없음) 프로젝트를 바꾸면 이전 필터를 새 값으로 교체한다", async () => {
    // 직접 진입: 현재는 a, 목록은 아직 없음
    setState({ enabled: true, current: "a", currentProject: undefined });
    const router = createMemoryRouter([{ path: "/logs", element: <LogProjectNote filterParam="project" /> }], { initialEntries: ["/logs?prj=a&project=a"] });
    render(
      <StorageProvider storage={createSafeStorage(null)}>
        <RouterProvider router={router} />
      </StorageProvider>,
    );
    // 목록 로드: 로그 필터 값은 프로젝트 id 자신(33m: project=<id>)
    act(() => setState({ enabled: true, current: "a", currentProject: project("a") }));
    // b로 전환(주소의 현재 프로젝트 쿼리가 먼저 정리된다)
    await act(async () => {
      await router.navigate("/logs?prj=b&project=a", { replace: true });
      setState({ enabled: true, current: "b", currentProject: project("b") });
    });
    await waitFor(() => expect(router.state.location.search).toContain("project=b"));
    expect(router.state.location.search).not.toContain("project=a");
    expect(router.state.location.search).toContain("prj=b");
  });
});

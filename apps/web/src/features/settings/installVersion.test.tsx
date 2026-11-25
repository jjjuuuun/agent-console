import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import pkg from "../../../package.json";

afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe("설정 › 설치: 표시 버전", () => {
  it("빌드가 넣어 주는 VITE_APP_VERSION을 그대로 보인다", async () => {
    vi.stubEnv("VITE_APP_VERSION", pkg.version);
    const { InstallSection } = await import("./sections/InstallSection");
    render(<InstallSection onApplyUpdate={() => undefined} />);
    expect(screen.getByText(`현재 버전 ${pkg.version}`)).toBeTruthy();
  });

  it("웹 package.json 버전은 1.0.0 릴리스 줄기다", () => {
    expect(pkg.version).toMatch(/^1\./);
  });
});

import { describe, expect, it } from "vitest";
import { contractsCompat } from "./contractsCompat";

describe("contractsCompat", () => {
  it("같은 값이거나 서버 값이 비어 있으면 호환", () => {
    expect(contractsCompat("0.12.0", "0.12.0")).toEqual({ compatible: true });
    expect(contractsCompat("", "0.12.0")).toEqual({ compatible: true });
  });

  it("0.x는 패치 차이만 호환(사내 ^0.y.z 범위와 같은 기준)", () => {
    expect(contractsCompat("0.12.1", "0.12.0")).toEqual({ compatible: true });
    expect(contractsCompat("0.12.0", "0.12.3")).toEqual({ compatible: true });
    expect(contractsCompat("0.11.0", "0.12.0")).toEqual({ compatible: false, older: "server" });
    expect(contractsCompat("0.13.0", "0.12.4")).toEqual({ compatible: false, older: "web" });
  });

  it("1.0 이상은 major가 같으면 호환", () => {
    expect(contractsCompat("1.4.0", "1.2.9")).toEqual({ compatible: true });
    expect(contractsCompat("2.0.0", "1.9.0")).toEqual({ compatible: false, older: "web" });
  });

  it("해석할 수 없는 값은 같을 때만 호환이고 어느 쪽이 낡았는지 모른다", () => {
    expect(contractsCompat("dev", "0.12.0")).toEqual({ compatible: false, older: null });
    expect(contractsCompat("0.0.0-other", "0.12.0")).toEqual({ compatible: false, older: "server" });
  });
});

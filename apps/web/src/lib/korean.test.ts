import { describe, expect, it } from "vitest";
import { objectParticle } from "./korean";

describe("objectParticle", () => {
  it("받침에 따라 을/를을 고른다", () => {
    expect(objectParticle("도우미")).toBe("를");
    expect(objectParticle("백엔드")).toBe("를");
    expect(objectParticle("디자인팀")).toBe("을");
    expect(objectParticle("PL")).toBe("을(를)");
    expect(objectParticle("")).toBe("을(를)");
  });
});

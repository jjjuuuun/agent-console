import { describe, expect, test } from "vitest";

import { createI18n, overlayMessages } from "@agent-console/i18n";

const bundled = {
  en: { lib: { goto: { _: "Go to line", issue: "Go to issue" }, plain: "Plain" } },
  ko: { lib: { goto: { _: "줄로 이동", issue: "문제로 이동" }, plain: "일반" } },
};

describe("overlayMessages with group text", () => {
  test("a flat default key that is a message and a group in the catalog takes the group's `_` text", () => {
    const i18n = createI18n({ language: "en", bundled });
    const defaults = { goto: "줄로 이동", "goto.issue": "문제로 이동", plain: "일반" };
    expect(overlayMessages(i18n, "lib", defaults)).toEqual({ goto: "Go to line", "goto.issue": "Go to issue", plain: "Plain" });
  });
});

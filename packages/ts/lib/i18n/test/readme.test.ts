import { expect, test } from "vitest";

// README "Minimal use"의 ```ts readme 블록과 아래 표시 구간이 같아야 한다(`pnpm pkg-lint`가 검사).
// readme:start
import { createI18n, resolveLanguage } from "@agent-console/i18n";

const language = resolveLanguage({ browser: ["ko-KR"], available: ["en", "ko"] });
const i18n = createI18n({
  language,
  bundled: {
    en: { app: { greeting: "Open {label}" } },
    ko: { app: { greeting: "{label, particle.object} 엽니다" } },
  },
});
const text = i18n.t("greeting", { ns: "app", replace: { label: "팀" } });
// readme:end

test("README 예제가 실제로 돈다", () => {
  expect(language).toBe("ko");
  expect(text).toBe("팀을 엽니다");
});

import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { assertCatalogsMatch } from "@agent-console/i18n/testing";
import type { MessageTree } from "@agent-console/i18n";
import { bootBundles, bundledLanguages, loadBundled } from "./bundles";
import { LIB_LOCALES } from "./libLocales";

const root = join(__dirname, "..", "locales");
const read = (lang: string, ns: string) => JSON.parse(readFileSync(join(root, lang, `${ns}.json`), "utf8")) as MessageTree;

describe("앱 묶음(import.meta.glob)", () => {
  it("언어 목록은 locales/<언어>/ 폴더에서 읽는다(코드에 목록 없음)", () => {
    expect(bundledLanguages()).toEqual(readdirSync(root).sort());
  });

  it("부팅 묶음은 모든 언어 것이 첫 청크에 동기로 들어 있다", () => {
    const boot = bootBundles();
    for (const lang of bundledLanguages()) expect(Object.keys(boot[lang] ?? {})).toEqual(["boot"]);
  });

  it("ko·en은 네임스페이스·키·자리표시자가 같고 영어는 조사 서식을 쓰지 않는다(W2)", () => {
    const names = (lang: string) => readdirSync(join(root, lang)).sort();
    expect(names("en")).toEqual(names("ko"));
    for (const file of names("ko")) {
      const ns = file.replace(/\.json$/, "");
      assertCatalogsMatch(read("ko", ns), read("en", ns));
    }
  });

  it("loadBundled는 앱 묶음 + 라이브러리 묶음을 한 번에 돌려주고, 없는 언어는 undefined", async () => {
    const en = await loadBundled("en");
    expect(Object.keys(en ?? {})).toEqual(expect.arrayContaining(["settings", ...Object.keys(LIB_LOCALES)]));
    expect((en?.["settings"] as { language: { label: string } }).language.label).toBe("Language");
    expect(await loadBundled("xx-none")).toBeUndefined();
  });
});

import { availableLanguages, languageName, matchLanguage, resolveLanguage, useT } from "@agent-console/i18n";
import { Banner, Button } from "@agent-console/ui";
import { LanguageSelect, type LanguageOption, type LanguageSelectMessages } from "./LanguageSelect";
import { FALLBACK_LANGUAGE } from "./languageStorage";
import { useLanguage } from "./LanguageContext";

/** 코드순 정렬(이름이 아니라 코드라서 언어를 바꿔도 행이 움직이지 않는다). */
const byCode = new Intl.Collator("en", { numeric: true });

/**
 * 설정 › 화면의 언어 고르기(컨테이너). 선택지 = 앱 묶음 ∪ 서버 `GET /i18n`, 이름은 `Intl.DisplayNames`다.
 * 바꾸면 저장 단추 없이 즉시 반영·저장한다(`LanguageProvider`가 순서를 맡는다). 공급자가 없으면 아무것도 그리지 않는다.
 */
export function LanguageSetting() {
  const language = useLanguage();
  const t = useT("settings");
  const current = t.language;
  const messages: LanguageSelectMessages = {
    label: t("language.listLabel"),
    auto: t("language.auto"),
    autoNow: (name) => t("language.autoNow", { name }),
    autoFallback: (code, name) => t("language.autoFallback", { code, name }),
    partial: t("language.partial"),
    partialHint: (name, missing) =>
      typeof missing === "number" && missing > 0 ? t("language.partialCount", { name, count: missing }) : t("language.partialHint", { name }),
    sources: (sources) => t("language.sources", { list: sources }),
    unavailable: (code) => t("language.unavailable", { code }),
    unavailableHelp: t("language.unavailableHelp"),
    loading: t("language.loading"),
    search: t("language.search"),
    pending: t("language.pending"),
  };

  // 선택지는 몇 개뿐이라 렌더마다 만든다(문구 묶음이 바뀌는 때를 따로 추적하지 않는다).
  const view = (() => {
    if (language === null) return null;
    const { info, bundled, browser, state } = language;
    const available = availableLanguages(bundled, info);
    const byServer = new Map((info?.languages ?? []).map((l) => [l.code, l]));
    const options: LanguageOption[] = [...available].sort(byCode.compare).map((code) => {
      const server = byServer.get(code);
      return {
        code,
        name: languageName(code),
        aliases: [languageName(code, current)],
        complete: server?.complete ?? true,
        missing: server?.missing,
        sources: server?.sources ?? [],
      };
    });
    const resolved = resolveLanguage({ browser, available, serverDefault: info?.default_language ?? null, fallback: FALLBACK_LANGUAGE });
    const first = browser[0];
    const note =
      first !== undefined && matchLanguage(first, available) === undefined
        ? messages.autoFallback(first, languageName(resolved, current))
        : undefined;
    const saved = state.preference;
    const matched = typeof saved === "string" ? (matchLanguage(saved, available) ?? saved) : null;
    return {
      options,
      value: matched,
      unavailable: typeof saved === "string" && matchLanguage(saved, available) === undefined ? saved : undefined,
      autoHint: { resolvedName: languageName(resolved), note },
      fallbackName: languageName(info?.fallback_language ?? FALLBACK_LANGUAGE),
    };
  })();

  if (language === null || view === null) return null;
  const { state, infoStatus, select, retrySave } = language;
  return (
    <div className="app-lang-setting">
      <LanguageSelect
        options={view.options}
        value={view.value}
        autoHint={view.autoHint}
        fallbackName={view.fallbackName}
        pending={state.pending}
        unavailableValue={view.unavailable}
        loading={infoStatus === "loading"}
        onChange={select}
        messages={messages}
      />
      {infoStatus === "unavailable" ? <p className="app-muted app-lang-note">{t("language.serverTextOriginal")}</p> : null}
      {state.serverTextFailed ? <Banner tone="info">{t("language.serverTextFailed")}</Banner> : null}
      {state.saveFailed ? (
        <Banner tone="warning" actions={<Button size="sm" onClick={retrySave}>{t("language.retry")}</Button>}>
          {t("language.saveFailed")}
        </Banner>
      ) : null}
    </div>
  );
}

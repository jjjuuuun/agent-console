import { useId } from "react";
import { useT } from "@agent-console/i18n";
import { Icon, THEME_CYCLE, useTheme } from "@agent-console/ui";
import { LanguageSetting, useLanguage } from "../../../i18n";

/**
 * 화면 설정: 언어(설정 문서의 `ui.language`, 바꾸면 즉시 반영·저장)와 테마(이 브라우저에만 저장).
 * 이 섹션은 설정 화면의 "한 번에 저장" 묶음 밖이다.
 */
export function AppearanceSection() {
  const t = useT("settings");
  const { theme, setTheme } = useTheme();
  const hasLanguage = useLanguage() !== null;
  const languageId = useId();
  const themeId = useId();
  return (
    <div className="app-appearance">
      {hasLanguage ? (
        <section className="app-appearance-item" aria-labelledby={languageId}>
          <h3 id={languageId} className="app-appearance-label">{t("language.label")}</h3>
          <p className="app-muted app-appearance-help">{t("language.help")}</p>
          <LanguageSetting />
        </section>
      ) : null}
      <section className="app-appearance-item" aria-labelledby={themeId}>
        <h3 id={themeId} className="app-appearance-label">{t("appearance.themeLabel")}</h3>
        <p className="app-muted app-appearance-help">{t("appearance.themeHelp")}</p>
        <div role="radiogroup" aria-label={t("appearance.themeLabel")} className="app-theme-radios">
          {THEME_CYCLE.map((choice) => (
            <label key={choice} className="app-theme-radio">
              <input type="radio" name="theme" value={choice} checked={theme === choice} onChange={() => setTheme(choice)} />
              <Icon name={`theme-${choice}`} />
              <span>{t(`appearance.theme.${choice}`)}</span>
              {choice === "system" ? <span className="app-muted"> {t("appearance.systemHint")}</span> : null}
            </label>
          ))}
        </div>
      </section>
    </div>
  );
}

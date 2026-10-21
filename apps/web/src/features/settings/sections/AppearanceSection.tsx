import { Icon, THEME_CYCLE, useTheme } from "@agent-console/ui";
import { messages as m } from "../../../app/messages";

/** 화면 설정: 테마 라디오(시스템·라이트·다크). 이 브라우저에만 저장되며 설정 문서와 무관하다. */
export function AppearanceSection() {
  const { theme, setTheme } = useTheme();
  return (
    <div role="radiogroup" aria-label={m.settings.appearance.themeLabel} className="app-theme-radios">
      {THEME_CYCLE.map((choice) => (
        <label key={choice} className="app-theme-radio">
          <input type="radio" name="theme" value={choice} checked={theme === choice} onChange={() => setTheme(choice)} />
          <Icon name={`theme-${choice}`} />
          <span>{m.theme.names[choice]}</span>
          {choice === "system" ? <span className="app-muted"> {m.settings.appearance.systemHint}</span> : null}
        </label>
      ))}
    </div>
  );
}

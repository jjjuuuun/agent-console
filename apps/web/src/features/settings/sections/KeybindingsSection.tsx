import { useEffect, useMemo, useRef, useState } from "react";
import { computeEffectiveKeys, isPlainCharCombo, splitKeySequence, SEQUENCE_TIMEOUT_MS, useEffectiveShortcuts, type KeyPlatform } from "@agent-console/ui";
import { Button } from "@agent-console/ui";
import type { WorkspaceSettings } from "@agent-console/contracts";
import { messages as m } from "../../../app/messages";
import { checkKeybinding, comboFromEvent, isPlainKeys } from "../../../lib/keybindings";
import { shortcutKeysText, shortcutLabel } from "../../../shell/HelpDialog";
import { useShortcutEnvironment } from "../../../shell/shortcutDefaults";
import type { SectionEditProps } from "./FormSections";
import { isImeKeyEvent } from "../../../lib/ime";

/**
 * 새 키 조합을 입력받는다. 수식키 조합은 한 번에, 단일 문자 키는 1초 안에 두 번째 키가 오면 시퀀스(`g c`)로 묶는다.
 * `Esc`는 취소.
 */
export function KeyCapture({ platform, label, onCapture, onCancel }: { platform: KeyPlatform; label: string; onCapture: (keys: string) => void; onCancel: () => void }) {
  const first = useRef<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(
    () => () => {
      if (timer.current !== null) clearTimeout(timer.current);
    },
    [],
  );
  return (
    <div
      role="textbox"
      aria-readonly="true"
      aria-label={label}
      tabIndex={0}
      className="app-keycapture"
      ref={(el) => el?.focus()}
      onKeyDown={(e) => {
        if (isImeKeyEvent(e)) return;
        e.preventDefault();
        e.stopPropagation();
        if (e.key === "Escape") return onCancel();
        const combo = comboFromEvent(e, platform);
        if (combo === undefined) return;
        if (first.current !== null) {
          if (timer.current !== null) clearTimeout(timer.current);
          const keys = `${first.current} ${combo}`;
          first.current = null;
          return onCapture(keys);
        }
        if (isPlainCharCombo(combo, platform)) {
          first.current = combo;
          timer.current = setTimeout(() => {
            const keys = first.current;
            first.current = null;
            if (keys !== null) onCapture(keys);
          }, SEQUENCE_TIMEOUT_MS);
          return;
        }
        onCapture(combo);
      }}
    >
      {m.settings.keybindings.capturing}
    </div>
  );
}

/** ③ 단축키 섹션 (`ui.keybindings`). 충돌·예약 키·수식키 필요는 경고만 하고 저장은 막지 않는다. */
export function KeybindingsSection({ value, onChange, disabled }: SectionEditProps) {
  const { defaultKeys, platform } = useShortcutEnvironment();
  const registered = useEffectiveShortcuts();
  const overrides = useMemo(() => (value.ui?.keybindings ?? {}) as Record<string, string>, [value.ui?.keybindings]);
  const [capturing, setCapturing] = useState<string | null>(null);
  const t = m.settings.keybindings;

  const rows = useMemo(() => {
    const defs = registered.map((e) => ({
      id: e.id,
      scope: e.scope,
      titleKey: e.titleKey,
      keys: defaultKeys[e.id] ?? (e.isDefault ? e.keys : e.keys),
      ...(e.modifierRequired === undefined ? {} : { modifierRequired: e.modifierRequired }),
    }));
    return computeEffectiveKeys(defs, overrides, platform).map((e) => ({ ...e, defaultKeys: defs.find((d) => d.id === e.id)?.keys ?? "" }));
  }, [registered, defaultKeys, overrides, platform]);

  const setKeys = (id: string, keys: string | null) => {
    const next = { ...overrides };
    if (keys === null) delete next[id];
    else next[id] = keys;
    const ui = { ...(value.ui ?? {}), keybindings: Object.keys(next).length === 0 ? null : next } as WorkspaceSettings["ui"];
    onChange({ ...value, ui });
  };

  if (rows.length === 0) return <p className="app-muted">{t.empty}</p>;
  const anyPlain = rows.some((row) => row.keys !== "" && isPlainKeys(row.keys, platform));
  return (
    <>
    {anyPlain ? <p className="app-muted app-overridable">{t.plain}</p> : null}
    <table className="app-table" aria-label={t.table}>
      <thead>
        <tr>
          <th>{t.command}</th>
          <th>{t.current}</th>
          <th>{t.defaultKey}</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => {
          const issues = checkKeybinding(row, platform);
          const title = shortcutLabel(row);
          return (
            <tr key={row.id}>
              <td>{title}</td>
              <td>
                {capturing === row.id ? (
                  <KeyCapture
                    platform={platform}
                    label={t.capture(title)}
                    onCancel={() => setCapturing(null)}
                    onCapture={(keys) => {
                      setCapturing(null);
                      setKeys(row.id, keys);
                    }}
                  />
                ) : (
                  <>
                    <kbd>{shortcutKeysText(row.keys, platform)}</kbd>
                    {row.keys !== "" && isPlainKeys(row.keys, platform) ? <span className="app-muted app-plainkey" title={t.plain}>{t.plainMark}</span> : null}
                    {issues.map((issue) => (
                      <div key={issue} className="app-sev" data-severity="warning" role="note">
                        ▲ {t.issues[issue]}
                      </div>
                    ))}
                  </>
                )}
              </td>
              <td className="app-muted"><kbd>{shortcutKeysText(row.defaultKeys, platform)}</kbd></td>
              <td>
                <div className="app-inline-actions">
                  <Button size="sm" disabled={disabled} onClick={() => setCapturing(row.id)}>{t.change}</Button>
                  <Button size="sm" disabled={disabled || splitKeySequence(row.keys).length === 0} onClick={() => setKeys(row.id, "")}>{t.disable}</Button>
                  <Button size="sm" disabled={disabled || !(row.id in overrides)} onClick={() => setKeys(row.id, null)}>{t.reset}</Button>
                </div>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
    </>
  );
}

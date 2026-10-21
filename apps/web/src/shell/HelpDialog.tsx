import { Button, Dialog, formatKeyCombo, splitKeySequence, useEffectiveShortcuts, isPlainCharCombo, type EffectiveShortcut, type KeyPlatform } from "@agent-console/ui";
import { lookupMessage, messages as m } from "../app/messages";
import { routeIdOfGoto } from "./routeConfig";

/** 표시용 단축키 이름. `g` 이동 명령은 "○○(으)로 이동", 나머지는 `titleKey` 그대로. */
export function shortcutLabel(entry: Pick<EffectiveShortcut, "id" | "titleKey">): string {
  return routeIdOfGoto(entry.id) === undefined ? lookupMessage(entry.titleKey) : m.shortcuts.gotoPrefix(lookupMessage(entry.titleKey));
}

/** 키 문자열 표시(`g c` → `G C`가 아니라 `g c`, 조합은 플랫폼 표기). */
export function shortcutKeysText(keys: string, platform: KeyPlatform): string {
  if (keys === "") return m.shortcuts.disabled;
  return splitKeySequence(keys)
    .map((k) => formatKeyCombo(k, platform))
    .join(" ");
}

export interface HelpDialogProps {
  /** "앱 서버 연결: 연결됨 — …" 한 줄(없으면 그리지 않음) */
  connectionNote?: string;
  open: boolean;
  onClose: () => void;
  /** 현재 화면의 범위 id(그 범위로 등록된 단축키를 위에 보인다) */
  scope: string | undefined;
  /** 같은 화면에 속한 추가 단축키 범위(라우트 `shortcutScopes`) */
  extraScopes?: readonly string[];
  platform: KeyPlatform;
  onReplayHints: () => void;
  /** 있으면 맨 위에 "시작 순서 다시 보기"를 둔다(첫 단계 안내를 다시 연다). */
  onShowStart?: () => void;
  /** 표에서 뺄 단축키 id(꺼진 화면으로 가는 `g` 키 등) */
  hiddenIds?: ReadonlySet<string>;
}

function Table({ title, rows, platform }: { title: string; rows: readonly EffectiveShortcut[]; platform: KeyPlatform }) {
  return (
    <section aria-label={title}>
      <h3 className="app-block-subtitle">{title}</h3>
      <table className="app-help-table">
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <th scope="row">
                <kbd>{shortcutKeysText(row.keys, platform)}</kbd>
              </th>
              <td>
                {shortcutLabel(row)}
                {row.keys !== "" && splitKeySequence(row.keys).some((k) => isPlainCharCombo(k, platform)) ? <span className="app-muted"> · {m.shortcuts.plain}</span> : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

/** 단축키 도움말(`?`). 표는 실제 적용 중인 키(설정이 덮어쓴 값)에서 생성한다. */
export function HelpDialog({ open, onClose, scope, extraScopes = [], platform, onReplayHints, onShowStart, hiddenIds, connectionNote }: HelpDialogProps) {
  const all = useEffectiveShortcuts().filter((e) => !hiddenIds?.has(e.id));
  const screen = all.filter((e) => e.scope !== "global" && (e.scope === scope || extraScopes.includes(e.scope)));
  const global = all.filter((e) => e.scope === "global");
  return (
    <Dialog
      open={open}
      title={m.shortcuts.helpTitle}
      onClose={onClose}
      wide
      actions={
        <>
          <Button onClick={onReplayHints}>{m.shortcuts.replayHints}</Button>
          <Button variant="primary" onClick={onClose}>
            {m.common.close}
          </Button>
        </>
      }
    >
      {connectionNote === undefined ? null : <p className="app-muted app-help-conn">{connectionNote}</p>}
      {onShowStart === undefined ? null : (
        <p>
          <Button onClick={onShowStart}>{m.shortcuts.replayStart}</Button>
        </p>
      )}
      {screen.length > 0 ? <Table title={m.shortcuts.helpThisScreen} rows={screen} platform={platform} /> : null}
      <Table title={m.shortcuts.helpGlobal} rows={global} platform={platform} />
      <section aria-label={m.shortcuts.helpFixed}>
        <h3 className="app-block-subtitle">{m.shortcuts.helpFixed}</h3>
        <table className="app-help-table">
          <tbody>
            <tr>
              <th scope="row">
                <kbd>Esc</kbd>
              </th>
              <td>
                {m.shortcuts.escName} <span className="app-muted">· {m.shortcuts.escLayers}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </section>
    </Dialog>
  );
}

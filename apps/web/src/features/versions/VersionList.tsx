import { useRef, useState, type KeyboardEvent } from "react";
import type { DefinitionVersion } from "@agent-console/contracts";
import { Button, Tag } from "@agent-console/ui";
import { formatDateTime, formatRelative, shortId } from "../../lib/format";
import { isImeKeyEvent } from "../../lib/ime";
import { ActionMenu } from "../library";
import { versionMessages as t } from "./messages";
import type { CompareMode } from "./versionsLogic";

export interface VersionListProps {
  /** 최신순(0번 = 현재) */
  versions: readonly DefinitionVersion[];
  /** 현재 시각(ms), 상대 시간 표시용 */
  now: number;
  checked: readonly string[];
  mode: CompareMode;
  onModeChange: (mode: CompareMode) => void;
  /** 체크 토글(현재와 모드: 그 버전 하나만 선택) */
  onToggle: (hash: string) => void;
  /** 이 버전을 현재와 비교 */
  onCompareCurrent: (hash: string) => void;
  /** 체크한 두 버전 비교(`D`) */
  onComparePair: () => void;
  onRestore: (hash: string) => void;
  onViewRaw: (hash: string) => void;
  onCopyHash: (hash: string) => void;
  /** 처음 보일 개수 */
  pageSize?: number;
}

/** 버전 목록(체크박스 최대 2, 키보드 `↑↓ Space Enter D R`). 서버·비교 계산을 모른다. */
export function VersionList({ versions, now, checked, mode, onModeChange, onToggle, onCompareCurrent, onComparePair, onRestore, onViewRaw, onCopyHash, pageSize = 20 }: VersionListProps) {
  const [shown, setShown] = useState(pageSize);
  const [active, setActive] = useState(0);
  const rows = useRef(new Map<string, HTMLDivElement>());
  const visible = versions.slice(0, shown);
  const activeAt = Math.min(active, Math.max(visible.length - 1, 0));

  const focusAt = (i: number) => {
    const v = visible[i];
    if (v === undefined) return;
    setActive(i);
    rows.current.get(v.version_hash)?.focus();
  };
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>, hash: string, i: number) => {
    // 행 안의 버튼·입력에서 온 키는 그 요소가 처리한다(단일 문자 키는 입력창에서 무시).
    if ((e.target as HTMLElement) !== e.currentTarget) return;
    if (isImeKeyEvent(e) || e.ctrlKey || e.metaKey || e.altKey) return;
    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        focusAt(Math.min(i + 1, visible.length - 1));
        break;
      case "ArrowUp":
        e.preventDefault();
        focusAt(Math.max(i - 1, 0));
        break;
      case " ":
        e.preventDefault();
        onToggle(hash);
        break;
      case "Enter":
        e.preventDefault();
        onCompareCurrent(hash);
        break;
      case "d":
      case "D":
        e.preventDefault();
        onComparePair();
        break;
      case "r":
      case "R":
        e.preventDefault();
        onRestore(hash);
        break;
    }
  };

  return (
    <div className="ver-list-pane">
      <div role="radiogroup" aria-label={t.mode.label} className="ver-mode">
        {(["current", "pair"] as const).map((m) => (
          <label key={m} className="ver-mode-opt">
            <input type="radio" name="ver-mode" checked={mode === m} onChange={() => onModeChange(m)} /> {t.mode[m]}
          </label>
        ))}
      </div>
      <div role="listbox" aria-label={t.list.label} aria-multiselectable="true" className="ver-list">
        {visible.map((v, i) => {
          const hash8 = shortId(v.version_hash);
          const isCurrent = i === 0;
          const isChecked = checked.includes(v.version_hash);
          return (
            <div
              key={v.version_hash}
              ref={(el) => {
                if (el) rows.current.set(v.version_hash, el);
                else rows.current.delete(v.version_hash);
              }}
              role="option"
              aria-selected={isChecked}
              tabIndex={i === activeAt ? 0 : -1}
              className="ver-item"
              data-checked={isChecked ? "true" : undefined}
              onFocus={() => setActive(i)}
              onKeyDown={(e) => onKeyDown(e, v.version_hash, i)}
              onClick={(e) => {
                if ((e.target as HTMLElement).closest("button, input, [role=menu]")) return;
                onCompareCurrent(v.version_hash);
              }}
            >
              <input
                type="checkbox"
                tabIndex={-1}
                checked={isChecked}
                disabled={mode === "current" && isCurrent}
                aria-label={t.list.checkLabel(hash8)}
                onChange={() => onToggle(v.version_hash)}
              />
              <span className="lib-mono">{hash8}</span>
              {isCurrent ? <Tag>{t.list.currentChip}</Tag> : null}
              <span className="app-muted ver-time" title={formatDateTime(v.saved_at)}>
                {formatRelative(v.saved_at, now)}
              </span>
              <span className="ver-msg ac-ellipsis" title={v.message ?? ""}>
                {v.message ?? ""}
              </span>
              <ActionMenu
                label={`${t.list.rowMenu} ${hash8}`}
                items={[
                  { id: "raw", label: t.menu.viewRaw, onSelect: () => onViewRaw(v.version_hash) },
                  { id: "copy", label: t.menu.copyHash, onSelect: () => onCopyHash(v.version_hash) },
                  { id: "restore", label: t.menu.restore, disabled: isCurrent, onSelect: () => onRestore(v.version_hash) },
                ]}
              />
            </div>
          );
        })}
      </div>
      {versions.length > shown ? <Button onClick={() => setShown(shown + pageSize)}>{t.list.more}</Button> : null}
      <p className="app-muted ver-keys">{t.list.keysHint}</p>
    </div>
  );
}

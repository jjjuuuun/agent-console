import { useEffect, useRef, useState, type ReactElement } from "react";

import { Icon } from "./icons";
import type { Translate } from "./messages";

export interface SelectedFolderProps {
  id: string;
  t: Translate;
  /** 선택한 경로. 비면 자리 문구를 보인다. */
  path: string;
  /** 위 제목을 가린다. */
  hideLabel?: boolean;
  /** 제목 문구(기본 `folder.path.label`). */
  label?: string;
  /** 클립보드에 쓰는 함수(기본 `navigator.clipboard.writeText`, 없으면 [복사]를 그리지 않는다). */
  copy?: (text: string) => Promise<void> | void;
}

const COPIED_MS = 1500;

/** 선택한 폴더 상자: 선택 전에는 점선 자리, 선택하면 폴더 아이콘 + 전체 경로(줄바꿈) + [복사]. 최소 높이가 같아 아래가 움직이지 않는다. */
export function SelectedFolder({ id, t, path, hideLabel, label, copy }: SelectedFolderProps): ReactElement {
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);
  const filled = path.trim() !== "";
  const writer = copy ?? (typeof navigator !== "undefined" && navigator.clipboard ? (s: string) => navigator.clipboard.writeText(s) : null);
  const labelId = `${id}-label`;
  const onCopy = () => {
    if (!writer) return;
    void Promise.resolve(writer(path)).then(() => {
      setCopied(true);
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => setCopied(false), COPIED_MS);
    }, () => undefined);
  };
  return (
    <>
      <div id={labelId} className={hideLabel ? "ac-fp-sr" : "ac-fp-label"}>{label ?? t("folder.path.label")}</div>
      <div className="ac-fp-selected" role="group" aria-labelledby={labelId} data-filled={filled ? "true" : "false"}>
        {filled ? (
          <>
            <Icon name="folder" />
            <span className="ac-fp-selected-path ac-fp-mono ac-mono-wrap">{path}</span>
            {writer ? (
              <button type="button" className="ac-fp-btn" data-size="sm" aria-label={t("folder.pick.copy")} onClick={onCopy}>
                {copied ? t("folder.pick.copied") : t("folder.pick.copy_short")}
              </button>
            ) : null}
          </>
        ) : (
          <span className="ac-fp-selected-empty">{t("folder.pick.empty")}</span>
        )}
      </div>
    </>
  );
}

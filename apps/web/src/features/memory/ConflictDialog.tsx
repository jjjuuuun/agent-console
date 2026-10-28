/**
 * 저장 충돌(412)·"새 버전 있음" 비교 대화상자. 왼쪽 서버 최신, 오른쪽 내 변경(`TextDiff`).
 * 내 변경을 저장해도 서버 버전은 기록에 남는다. 서버 버전 불러오기는 내 변경을 버린다(버튼 문구에 적는다).
 */
import { useRef, useState } from "react";
import { Button, Dialog } from "@agent-console/ui";
import { TextDiff } from "@agent-console/text-editor";
import type { MemoryEntry } from "@agent-console/contracts/memory";
import { languageForContentType } from "@agent-console/memory-view";
import { useStorage } from "../../app/StorageContext";
import { MEMORY_STORAGE } from "./memoryConfig";
import { memoryMessages as t } from "./messages";
import { relativeTime } from "./format";

export interface ConflictDialogProps {
  open: boolean;
  /** 내가 연 버전 */
  openedVersion: number;
  /** 서버 최신 항목 */
  server: MemoryEntry;
  /** 서버 최신 항목을 쓴 이 */
  serverAuthor: string;
  /** 내 본문 */
  mine: string;
  contentType: string | null | undefined;
  saving: boolean;
  onKeepEditing: () => void;
  onLoadServer: () => void;
  onSaveMine: () => void;
}

export function ConflictDialog({ open, openedVersion, server, serverAuthor, mine, contentType, saving, onKeepEditing, onLoadServer, onSaveMine }: ConflictDialogProps) {
  const storage = useStorage();
  const keepRef = useRef<HTMLButtonElement>(null);
  const [layout, setLayout] = useState<"split" | "unified" | "auto">(() => {
    const saved = storage.get(MEMORY_STORAGE.diffLayout);
    return saved === "split" || saved === "unified" ? saved : "auto";
  });
  return (
    <Dialog
      open={open}
      size="xl"
      title={t.conflict.title}
      onClose={onKeepEditing}
      initialFocus={keepRef}
      actions={
        <>
          <Button ref={keepRef} onClick={onKeepEditing}>{t.conflict.keepEditing}</Button>
          <Button variant="danger" onClick={onLoadServer} disabled={saving}>{t.conflict.loadServerLoseMine}</Button>
          <Button variant="primary" onClick={onSaveMine} loading={saving}>{t.conflict.saveMine(server.version + 1)}</Button>
        </>
      }
    >
      <p className="mem-conflict-line">
        {t.conflict.opened(openedVersion, server.version)} · {t.conflict.byWho(serverAuthor, relativeTime(server.updated_at))}
      </p>
      <div className="mem-conflict-heads" aria-hidden="true">
        <span>{t.conflict.server(server.version)}</span>
        <span>{t.conflict.mine}</span>
      </div>
      <TextDiff
        before={server.content}
        after={mine}
        language={languageForContentType(contentType)}
        ariaLabel={`${t.conflict.server(server.version)} / ${t.conflict.mine}`}
        mode={layout}
        unifiedBelow={900}
        maxHeight={320}
        onModeChange={(mode) => {
          setLayout(mode);
          storage.set(MEMORY_STORAGE.diffLayout, mode);
        }}
      />
      <p className="mem-help">{t.conflict.note(server.version)}</p>
    </Dialog>
  );
}

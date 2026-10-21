import { useState } from "react";
import type { VersionConflictDetails } from "@agent-console/contracts";
import { Banner, Button, Dialog } from "@agent-console/ui";
import { messages as m } from "../app/messages";
import { formatDateTime } from "../lib/format";

export interface ConflictBannerProps {
  details: VersionConflictDetails;
  busy: boolean;
  /** 서버 버전 불러오기(내 변경 폐기) */
  onLoadServer: () => void;
  /** 없으면 [사본으로 저장] 버튼을 숨긴다 */
  onSaveCopy?: () => void;
  /** 내 변경으로 덮어쓰기 */
  onOverwrite: () => void;
  /** 서버 수정 외에 덧붙일 요약(노드 수 등) */
  summary?: string;
}

type Confirm = "load" | "overwrite" | null;

/** 버전 충돌 배너(닫기 불가, 정의 편집 화면 공용). 파괴적 동작은 확인 다이얼로그를 거친다. */
export function ConflictBanner({ details, busy, onLoadServer, onSaveCopy, onOverwrite, summary }: ConflictBannerProps) {
  const [confirm, setConfirm] = useState<Confirm>(null);
  const t = m.definition.conflict;
  const info = [details.saved_at != null ? t.savedAt(formatDateTime(details.saved_at)) : undefined, summary].filter((x): x is string => x !== undefined);
  return (
    <>
      <Banner
        tone="warning"
        title={t.title}
        role="alert"
        aria-label={t.region}
        actions={
          <>
            <Button size="sm" variant="primary" disabled={busy} onClick={() => setConfirm("load")}>
              {t.loadServer}
            </Button>
            {onSaveCopy === undefined ? null : (
              <Button size="sm" disabled={busy} onClick={onSaveCopy}>
                {t.saveCopy}
              </Button>
            )}
            <Button size="sm" variant="danger" disabled={busy} onClick={() => setConfirm("overwrite")}>
              {t.overwrite}
            </Button>
          </>
        }
      >
        {t.body}
        {info.length > 0 ? <span className="app-muted"> {info.join(" · ")}</span> : null}
      </Banner>
      <Dialog
        open={confirm !== null}
        title={confirm === "overwrite" ? t.overwriteTitle : t.loadServerTitle}
        onClose={() => setConfirm(null)}
        actions={
          <>
            <Button onClick={() => setConfirm(null)}>{m.common.cancel}</Button>
            <Button
              variant="danger"
              onClick={() => {
                const which = confirm;
                setConfirm(null);
                if (which === "overwrite") onOverwrite();
                else onLoadServer();
              }}
            >
              {confirm === "overwrite" ? t.overwrite : t.loadServer}
            </Button>
          </>
        }
      >
        <p className="ac-text">{confirm === "overwrite" ? t.overwriteBody : t.loadServerBody}</p>
      </Dialog>
    </>
  );
}

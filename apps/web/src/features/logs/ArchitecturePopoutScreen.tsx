import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router";
import type { LogQueryParams } from "@agent-console/api-client";
import { Banner, Button } from "@agent-console/ui";
import { LINK_PART_IDS, useLinkPart } from "../../modules";
import { ARCH_POPOUT, ArchitecturePanel, archMessages as t, createArchSync, useArchSync, useArchitectureController, type ArchSyncMessage, type ChannelFactory } from "../architecture";
import { LogsLiveProvider, useLogsIngested } from "./LogsLive";
import { LOGS_LIMITS } from "./logsConfig";

/** 쿼리의 JSON 범위 인자를 읽는다. 값은 문자열 또는 문자열 배열만 받는다(모르는 모양은 버린다). */
export function parseScope(raw: string | null): LogQueryParams {
  if (raw === null || raw === "") return {};
  try {
    const v: unknown = JSON.parse(raw);
    if (typeof v !== "object" || v === null || Array.isArray(v)) return {};
    const out: Record<string, string | string[]> = {};
    for (const [k, val] of Object.entries(v)) {
      if (typeof val === "string") out[k] = val;
      else if (Array.isArray(val) && val.every((x) => typeof x === "string")) out[k] = val as string[];
    }
    return out;
  } catch {
    return {};
  }
}

export interface ArchitecturePopoutProps {
  /** 채널 만드는 함수(테스트 주입). 기본은 브라우저 `BroadcastChannel`. */
  channelFactory?: ChannelFactory;
  /** 이 창을 닫는 함수(테스트 주입). 기본은 `window.close()`. */
  closeWindow?: () => void;
}

/** 구조도 분리 창 화면(앱 셸 밖, `/popout/architecture`). 원래 창과 선택·강조를 주고받고 숫자는 실시간으로 갱신한다. */
export function ArchitecturePopoutScreen(props: ArchitecturePopoutProps) {
  return (
    <LogsLiveProvider>
      <PopoutBody {...props} />
    </LogsLiveProvider>
  );
}

function PopoutBody({ channelFactory, closeWindow }: ArchitecturePopoutProps) {
  const [params] = useSearchParams();
  const key = params.get(ARCH_POPOUT.queryKey) ?? "";
  const raw = params.get(ARCH_POPOUT.queryScope);
  const arch = useLinkPart(LINK_PART_IDS.logsArchitectureFlow);
  const [scope, setScope] = useState<LogQueryParams>(() => parseScope(raw));
  const [highlightUid, setHighlightUid] = useState<string | null>(null);
  const [linked, setLinked] = useState(false);
  const sync = useMemo(() => (key === "" ? null : createArchSync(key, channelFactory === undefined ? {} : { factory: channelFactory })), [key, channelFactory]);
  useEffect(() => () => sync?.close(), [sync]);

  const enabled = arch.visible && key !== "";
  const controller = useArchitectureController({ scope, enabled, highlightUid });
  const close = useCallback(() => (closeWindow ?? (() => window.close()))(), [closeWindow]);
  const onMessage = useCallback(
    (m: ArchSyncMessage) => {
      if (m.kind === "close") close();
      else if (m.kind === "state" || m.kind === "highlight" || m.kind === "scope") setLinked(true);
    },
    [close],
  );
  useArchSync({ sync, controller, role: "popout", onHighlight: setHighlightUid, onScope: setScope, onMessage });
  useLogsIngested((info) => controller.ingested(info.count), LOGS_LIMITS.archDebounceMs, enabled);

  // 열렸음을 알린다(원래 창이 지금 상태를 보내 준다). 닫힐 때 알려 원래 창이 구조도를 다시 붙인다.
  useEffect(() => {
    if (sync === null) return;
    sync.post({ kind: "hello" });
    const bye = () => sync.post({ kind: "bye" });
    window.addEventListener("pagehide", bye);
    return () => {
      window.removeEventListener("pagehide", bye);
      bye();
    };
  }, [sync]);
  useEffect(() => {
    document.title = t.popout.windowTitle(key);
  }, [key]);

  const redock = () => {
    sync?.post({ kind: "bye" });
    close();
  };
  return (
    <main className="arch-popout" data-screen="arch-popout" aria-label={t.region}>
      <header className="arch-popout-head">
        <h1 className="arch-popout-title">{t.popout.windowTitle(key)}</h1>
        <Button size="sm" onClick={redock} data-testid="arch-popout-close">{t.popout.redock}</Button>
      </header>
      {key === "" ? <Banner tone="warning">{t.popout.needKey}</Banner> : null}
      {key !== "" && !arch.visible ? <Banner tone="warning">{t.popout.needArch}</Banner> : null}
      {key !== "" && sync === null ? <Banner tone="warning">{t.popout.unsupported}</Banner> : null}
      {sync !== null && !linked ? <Banner tone="info" className="arch-popout-standalone">{t.popout.standalone}</Banner> : null}
      {enabled ? (
        <div className="arch-popout-body">
          <ArchitecturePanel controller={controller} hideEmptyHead={false} storageKeys={{ fit: "ac.arch.popout.fit", view: "ac.arch.popout.view" }} live />
        </div>
      ) : null}
    </main>
  );
}

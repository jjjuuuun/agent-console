import { useEffect, useRef, useState } from "react";
import { useNow } from "../../app/useNow";
import { useFormat } from "../../i18n";
import { useBackendConnectMessages, useOpenBackendConnect } from "../backendConnect";
import { discoveredCount, lineStateOf } from "./catalogView";
import { ModelCatalogLine } from "./ModelCatalogLine";
import { useBackendModelCatalog } from "./useBackendModelCatalog";

export interface ModelCatalogStatusProps {
  backendId: string | null | undefined;
  /** `form`: 모델 칸 아래 줄([연결 확인…] 있음). `dialog`: 연결 모달 카드 아래 줄 */
  variant?: "form" | "dialog";
  /** 값이 바뀌면(예: 로그인 성공 뒤 준비 상태가 갱신됨) 목록을 다시 읽는다. 첫 값은 무시한다 */
  refetchKey?: unknown;
}

/** 조회 문제의 사유 코드(`details.reason`). 없으면 undefined. */
function reasonCodeOf(issue: { details?: Record<string, unknown> | null | undefined } | undefined): string | undefined {
  const reason = issue?.details?.["reason"];
  return typeof reason === "string" && reason !== "" ? reason : undefined;
}

/**
 * 모델 목록 조회 상태 줄의 데이터 연결: 카탈로그 질의·새로 고침·연결 모달 열기를 `ModelCatalogLine`에 이어 준다.
 * 카탈로그 경로가 없는 옛 서버·질의 실패·백엔드 미선택이면 아무것도 그리지 않는다.
 */
export function ModelCatalogStatus({ backendId, variant = "form", refetchKey }: ModelCatalogStatusProps) {
  const m = useBackendConnectMessages().models;
  const fmt = useFormat();
  const openConnect = useOpenBackendConnect();
  const catalog = useBackendModelCatalog(backendId);
  const nowMs = useNow(true, 30_000);
  const [announcement, setAnnouncement] = useState("");

  const { refetch } = catalog;
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    void refetch();
  }, [refetchKey, refetch]);

  const baseState = lineStateOf(catalog.data, catalog.isFetching || catalog.refreshing);
  const state = baseState === "failed" && reasonCodeOf(catalog.data?.discovery?.issues?.[0]) === m.signInReason ? "signin" : baseState;
  if (state === null || backendId === null || backendId === undefined || backendId === "") return null;
  const discovery = catalog.data?.discovery ?? null;
  const count = discoveredCount(catalog.data?.models);
  const when = fmt.relative(discovery?.fetched_at ?? null, nowMs);

  let text: string;
  switch (state) {
    case "fetching": text = m.fetching; break;
    case "ok": text = count === 0 ? m.none : variant === "dialog" ? m.okDialog(count, when) : m.okForm(count, when); break;
    case "stale": text = m.stale(count, when); break;
    case "failed": text = m.failed; break;
    case "signin": text = m.signIn; break;
    case "disabled": text = m.disabled; break;
    default: text = m.unsupported;
  }
  const issue = discovery?.issues?.[0];
  // 앞 문구("모델 목록을 가져오지 못했습니다…")와 겹치지 않게 사유 코드만 짧게 보인다. 모르는 코드는 코드 그대로.
  const reasonCode = reasonCodeOf(issue);
  const reason = state === "failed" && reasonCode !== undefined && reasonCode !== "" ? (m.reason(reasonCode) ?? reasonCode) : undefined;

  const showRefresh = state !== "disabled" && !(variant === "dialog" && state === "unsupported");
  const showCheck = variant === "form" && openConnect !== undefined && (state === "stale" || state === "failed" || state === "unsupported" || state === "signin");
  const onRefresh = () => {
    void catalog.refresh().then((next) => {
      if (next === undefined) return;
      const s = next.discovery?.state;
      setAnnouncement(s === "ok" ? m.fetched(discoveredCount(next.models)) : text);
    });
  };
  return (
    <ModelCatalogLine
      state={state}
      text={text}
      reason={reason}
      variant={variant}
      refreshLabel={m.refresh}
      onRefresh={showRefresh ? onRefresh : undefined}
      refreshing={catalog.refreshing}
      checkLabel={m.check}
      moreLabel={m.moreActions}
      onCheck={showCheck ? () => openConnect({ focusBackend: backendId }) : undefined}
      announcement={announcement}
      data-testid={`model-catalog-${variant}`}
    />
  );
}

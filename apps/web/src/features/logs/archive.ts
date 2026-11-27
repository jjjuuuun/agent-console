import { createElement, useCallback } from "react";
import { useToast } from "@agent-console/ui";
import type { LogArchiveFormat, LogQueryParams } from "@agent-console/api-client";
import { useApi } from "../../app/ApiContext";
import { saveBlob } from "../../lib/download";
import { FILTER_KEYS } from "./logsConfig";
import { LogsToast } from "./LogsToast";

/** 브라우저 시간대(IANA 이름). 보관본 HTML의 시각 표시에 쓴다. */
export function browserTimeZone(): string | undefined {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || undefined;
  } catch {
    return undefined;
  }
}

/**
 * 보관본 내려받기: `GET /logs/archive`(첨부) → 파일 저장. 필터는 화면 전용 파라미터를 뺀 서버 필터만 받는다.
 * 실패하면 danger 토스트(서버 문장 그대로).
 */
export function useArchiveDownload(): (filter: LogQueryParams, format: LogArchiveFormat) => Promise<boolean> {
  const { rest } = useApi();
  const toast = useToast();
  return useCallback(
    async (filter, format) => {
      try {
        const tz = browserTimeZone();
        const file = await rest.downloadLogArchive({ filter, format, ...(tz === undefined ? {} : { tz }) });
        saveBlob(file.blob, file.filename ?? `logs.${format}`);
        const name = file.filename ?? `logs.${format}`;
        toast({ tone: "success", text: createElement(LogsToast, { render: (t) => t.sessions.archiveDone(name) }) });
        return true;
      } catch (e) {
        toast({ tone: "danger", text: createElement(LogsToast, { render: (t, d) => d(e, t.sessions.archiveFailed).message }) });
        return false;
      }
    },
    [rest, toast],
  );
}

/** 세션 하나의 보관본 필터(서버 필터 이름은 데이터 표에서). */
export function archiveFilterFor(session: string): LogQueryParams {
  return { [FILTER_KEYS.session]: session };
}

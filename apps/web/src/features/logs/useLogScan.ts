import { createElement, useCallback, useState } from "react";
import { useServerTranslate } from "../../i18n";
import { useQueryClient } from "@tanstack/react-query";
import { useToast } from "@agent-console/ui";
import type { LogScanReport, LogSourceInfo } from "@agent-console/contracts";
import { useApi } from "../../app/ApiContext";
import { logKeys } from "./useLogsApi";
import { LogsToast } from "./LogsToast";

export interface LogScan {
  scanning: boolean;
  /** `sourceIds`를 주면 그 출처만. 끝나면 모든 로그 질의를 무효화하고 결과 토스트를 띄운다. 보고서(실패하면 undefined)를 돌려준다. */
  run(sourceIds?: readonly string[]): Promise<LogScanReport | undefined>;
}

/** `POST /logs/scan` 호출 + 결과 토스트(보고서의 새 이벤트 수·출처별 오류 코드·메시지는 서버 값 그대로). */
export function useLogScan(sources?: readonly LogSourceInfo[], opts: { toast?: boolean } = {}): LogScan {
  const { rest } = useApi();
  const qc = useQueryClient();
  const toast = useToast();
  const [scanning, setScanning] = useState(false);
  const tr = useServerTranslate();
  const showToast = opts.toast ?? true;
  const run = useCallback(
    async (sourceIds?: readonly string[]) => {
      setScanning(true);
      try {
        const report = await rest.scanLogs(sourceIds);
        await qc.invalidateQueries({ queryKey: logKeys.root });
        if (showToast) {
          const failed = (report.sources ?? []).filter((s) => s.error_code != null);
          if (failed.length > 0) {
            const first = failed[0];
            const title = tr(sources?.find((s) => s.descriptor.id === first?.source_id)?.descriptor.title ?? first?.source_id ?? "");
            toast({ tone: "warning", text: createElement(LogsToast, { render: (t) => `${t.scanPartial(title, failed.length - 1)}${first?.message ? `: ${first.message}` : ""}` }) });
          } else {
            toast({ tone: "success", text: createElement(LogsToast, { render: (t) => t.scanDone(report.new_events ?? 0) }) });
          }
        }
        return report;
      } catch (e) {
        toast({ tone: "danger", text: createElement(LogsToast, { render: (t, d) => d(e, t.scanFailed).message }) });
        return undefined;
      } finally {
        setScanning(false);
      }
    },
    [rest, qc, toast, sources, showToast, tr],
  );
  return { scanning, run };
}

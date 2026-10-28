import { useEffect } from "react";
import { Link } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { useApi } from "../../app/ApiContext";
import { useApiQuery } from "../../app/queries";
import { ROUTE_ROLES, routePath } from "../library";
import { MEMORY_PARAMS, RUN_CHIPS } from "./memoryConfig";
import { memoryMessages as t } from "./messages";
import { chipNumber, countRunChips } from "./runChips";
import "./runChips.css";

export interface RunMemoryChipsProps {
  runId: string;
  /** 실행 중이면 이벤트가 들어오는 대로 1초 디바운스로 다시 센다 */
  active: boolean;
  /** 읽기 칩: 이 실행의 이벤트 목록을 접두로 연다(호출 쪽이 탭·주소 인자를 안다) */
  onOpenReads: (typePrefix: string) => void;
}

const chipKey = (runId: string) => ["memory", "run-chips", runId] as const;

/**
 * 실행 상세 요약 줄의 "메모리 쓰기 n · 읽기 m" 칩 한 쌍. 이 실행(자식 실행 제외)에 메모리 이벤트가 하나도 없으면 아무것도 그리지 않는다.
 * 쓰기 칩은 메모리 화면의 `author_run` 필터로 가는 링크이고, 숫자는 이벤트 type 접두(`memory.`)로 센다.
 */
export function RunMemoryChips({ runId, active, onOpenReads }: RunMemoryChipsProps) {
  const { ws } = useApi();
  const qc = useQueryClient();
  const events = useApiQuery(chipKey(runId), (rest) => rest.listRunEvents(runId, { type_prefix: RUN_CHIPS.typePrefix }), { meta: { silentBackgroundError: true }, retry: false });
  useEffect(() => {
    if (!active) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const sub = ws.subscribeRun(runId, (e) => {
      if (!e.type.startsWith(RUN_CHIPS.typePrefix)) return;
      timer ??= setTimeout(() => {
        timer = undefined;
        void qc.invalidateQueries({ queryKey: chipKey(runId) });
      }, RUN_CHIPS.debounceMs);
    });
    return () => {
      if (timer !== undefined) clearTimeout(timer);
      sub?.unsubscribe();
    };
  }, [active, ws, qc, runId]);
  if (events.data === undefined) return null;
  const { write, read } = countRunChips(events.data);
  if (write.count === 0 && read.count === 0) return null;
  const href = `${routePath(ROUTE_ROLES.memory)}?${MEMORY_PARAMS.authorRun}=${encodeURIComponent(runId)}`;
  const fail = (n: number) => (n > 0 ? <span className="mem-runchip-fail"><span className="app-sev" data-severity="warning" aria-hidden="true">▲</span> {t.runChips.failed(n)}</span> : null);
  return (
    <span className="mem-runchips" role="group" aria-label={t.runChips.label}>
      <span className="mem-runchip-item">
        <Link className="mem-runchip" to={href} title={t.runChips.writeTip}>{t.runChips.write(chipNumber(write.count))}</Link>
        {fail(write.failed)}
      </span>
      <span className="mem-runchip-item">
        <button type="button" className="mem-runchip" title={t.runChips.readTip} onClick={() => onOpenReads(RUN_CHIPS.read.openPrefix)}>{t.runChips.read(chipNumber(read.count))}</button>
        {fail(read.failed)}
      </span>
    </span>
  );
}

import { useLocation } from "react-router";
import { Link } from "react-router";
import { contractsSchema } from "@agent-console/contracts";
import { Button, Disclosure } from "@agent-console/ui";
import { logsMessages as t, useLogScan, useLogSources } from "../../logs";
import type { SectionEditProps } from "./FormSections";
import { LogsProjectsBlock } from "./logs/LogsProjectsBlock";
import { LogsSourcesBlock } from "./logs/LogsSourcesBlock";

function hasObserveSchema(): boolean {
  const def = contractsSchema.$defs["AgentSettings"] as { properties?: Record<string, unknown> } | undefined;
  return def?.properties?.["observe"] !== undefined;
}

/** 해시 `#logs?source=<id>` / `#logs/projects`에서 펼칠 블록과 출처 id를 읽는다(옛 `#logs/taxonomy`는 `sectionIdFromHash`가 분류 섹션으로 보낸다). */
function readHash(hash: string): { block: string | null; source: string | null } {
  const raw = hash.replace(/^#/, "");
  const [path = "", query = ""] = raw.split("?");
  const block = path.startsWith("logs/") ? path.slice("logs/".length) : null;
  const source = new URLSearchParams(query).get("source");
  return { block, source };
}

export interface LogsSectionProps extends SectionEditProps {
  /** 설정 문서에 저장 안 된 변경이 있는지 */
  dirty: boolean;
}

/** 설정 "로그 출처": 수집 출처 · 프로젝트 묶기(33p가 삭제). 분류 체계는 `LogTaxonomySection`(섹션 "로그 분류"). `logs.dashboards`는 이 화면이 그리지 않고(로그 > 대시보드에서 편집) 저장해도 그대로 둔다. */
export function LogsSection(props: LogsSectionProps) {
  const { hash } = useLocation();
  const target = readHash(hash);
  const sources = useLogSources();
  const scan = useLogScan(sources.data);
  const anyEnabled = (sources.data ?? []).some((s) => s.enabled);
  const sourcesErrors = (props.errors ?? []).filter((e) => e.path.startsWith("/logs/sources"));
  const projErrors = (props.errors ?? []).filter((e) => e.path.startsWith("/logs/projects"));
  const dot = (n: number) => (n > 0 ? <span className="app-sev" data-severity="error" role="img" aria-label={t.settings.errorDot}> ●</span> : null);
  return (
    <div className="logs-settings" id="logs-settings-body">
      <div className="logs-settings-top">
        <p className="app-muted">{t.settings.dashboardsNote} <Link to="/logs/dashboards">{t.settings.dashboardsLink}</Link></p>
        {anyEnabled ? <Button size="sm" loading={scan.scanning} disabled={props.dirty} title={props.dirty ? t.settings.sources.scanDirtyTip : undefined} onClick={() => void scan.run()}>{t.settings.scanAll}</Button> : null}
      </div>
      <Disclosure summary={<>{t.settings.blocks.sources}{dot(sourcesErrors.length)}</>} defaultOpen>
        <LogsSourcesBlock {...props} focusSource={target.source} observeHref={hasObserveSchema() ? "#common" : undefined} />
      </Disclosure>
      <Disclosure summary={<>{t.settings.blocks.projects}{dot(projErrors.length)}</>} {...(target.block === "projects" ? { defaultOpen: true } : {})}>
        <LogsProjectsBlock {...props} />
      </Disclosure>
    </div>
  );
}

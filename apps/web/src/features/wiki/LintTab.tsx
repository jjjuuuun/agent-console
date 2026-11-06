/**
 * 점검 탭(screen-wiki §8): 서버 점검 결과(`GET …/lint`)를 표로 보이고 심각도·코드·페이지로 거른다(거르기는 주소 `sev`·`code`·`q`).
 * 행을 열면 그 페이지(+줄)로 간다. [다시 점검] = 다시 읽기(`scan`) 뒤 점검을 다시 받는다. 링크 문법이 없으면 링크 점검이 없다는 안내를 표 위에 둔다.
 * 점검 코드·규칙 id·메시지는 서버 값이고 이름·톤 표는 앱 표시 표(`WikiDisplay`)가 준다.
 */
import { useCallback, useState } from "react";
import { useNavigate } from "react-router";
import { Banner, Button, useToast } from "@agent-console/ui";
import { LintTable, type LintFilter } from "@agent-console/wiki-view";
import type { WikiIssue } from "@agent-console/contracts/wiki";
import { useNow } from "../../app/useNow";
import { formatRelative } from "../../lib/format";
import { AnchoredMenu } from "./AnchoredMenu";
import { FailureBlock, ListSkeleton } from "./parts";
import { useWikiLint } from "./useWikiTabsApi";
import { useWikiSpace, useWikiSyntax } from "./useWikiApi";
import { SEVERITY_ORDER, WIKI_PARAMS } from "./wikiConfig";
import { wikiRulesPath } from "./wikiPaths";
import type { WikiTabProps } from "./wikiTabs";
import { wikiMessages as m } from "./messages";
import { wikiTabMessages } from "./tabMessages";

const t = wikiTabMessages.lint;
const P = WIKI_PARAMS;

/** 코드 거르기 값은 점검 결과에 실제 있는 코드만 의미가 있으므로 그대로 쓴다. 주소 값을 거르기 상태로. */
function filterFromParams(params: URLSearchParams): Partial<LintFilter> {
  const sev = params.get(P.severity);
  return { severities: sev === null || sev === "" ? [] : sev.split(","), code: params.get(P.code) ?? "", page: params.get(P.query) ?? "" };
}

export function LintTab({ wikiId, view, ctx, display, params, setParams, goTab, hasTab, refresh }: WikiTabProps) {
  const navigate = useNavigate();
  const lintQ = useWikiLint(wikiId);
  const syntaxQ = useWikiSyntax(wikiId);
  const space = useWikiSpace();
  const toast = useToast();
  const now = useNow(true, 60_000);
  const [checking, setChecking] = useState(false);
  const [menu, setMenu] = useState<{ issue: WikiIssue; x: number; y: number } | null>(null);
  const [initial] = useState(() => filterFromParams(params));

  const noSyntax = syntaxQ.data !== undefined && (syntaxQ.data.empty === true || (syntaxQ.data.syntax?.links ?? []).length === 0);
  const lintRules = view.rules?.lint_rules ?? 0;

  const openIssue = useCallback(
    (issue: WikiIssue, line: number | null) => {
      if (issue.path === undefined || issue.path === null || issue.path === "") return;
      goTab("page", { [P.path]: issue.path, ...(line === null ? {} : { [P.line]: String(line) }) });
    },
    [goTab],
  );
  const ruleOf = (issue: WikiIssue): string | null => {
    const id = issue.details?.["rule_id"];
    return typeof id === "string" && id !== "" ? id : null;
  };
  const lineOf = (issue: WikiIssue): number | null => {
    const v = issue.details?.["line"];
    return typeof v === "number" && Number.isFinite(v) ? v : null;
  };

  const onFilter = useCallback(
    (f: LintFilter) => {
      const next = new URLSearchParams(params);
      const put = (key: string, value: string) => (value === "" ? next.delete(key) : next.set(key, value));
      put(P.severity, f.severities.join(","));
      put(P.code, f.code);
      put(P.query, f.page);
      setParams(next, { replace: true });
    },
    [params, setParams],
  );

  /** 이슈를 만든 점검·쓰기 규칙 id → 그 항목을 준 위키 규칙 화면. 화면이 없으면 이 위키의 규칙 탭. */
  const openRule = (ruleId: string) => {
    const owner = (view.rules?.entries ?? []).find((e) => e.id === ruleId)?.rule_id;
    const to = owner === undefined ? undefined : wikiRulesPath(owner, ctx.projectId);
    if (to !== undefined) void navigate(to);
    else goTab("rules");
  };

  const recheck = async () => {
    setChecking(true);
    try {
      await space.client.scanWiki(wikiId);
      await lintQ.refetch();
      await refresh();
    } catch (e) {
      toast({ tone: "danger", text: e instanceof Error && e.message !== "" ? e.message : m.problem.generic });
    } finally {
      setChecking(false);
    }
  };

  const report = lintQ.data;
  const issues = report?.issues ?? [];
  const generated = report?.generated_at;
  const menuIssue = menu?.issue;
  const menuRule = menuIssue === undefined ? null : ruleOf(menuIssue);

  let body;
  if (lintQ.isPending) body = <ListSkeleton rows={8} />;
  else if (lintQ.isError || report === undefined) body = <FailureBlock error={lintQ.error} title={t.loadFailed} onRetry={() => void lintQ.refetch()} />;
  else if (issues.length === 0 && noSyntax && lintRules === 0) {
    body = (
      <Banner tone="info" data-testid="wiki-lint-none-enabled" actions={hasTab("rules") ? <Button size="sm" onClick={() => goTab("rules")}>{t.openRule}</Button> : undefined}>{t.noneEnabled}</Banner>
    );
  } else {
    body = (
      <LintTable
        issues={issues}
        display={display}
        severityOrder={SEVERITY_ORDER}
        lineOf={lineOf}
        ruleOf={ruleOf}
        initialFilter={initial}
        onFilterChange={onFilter}
        onOpen={openIssue}
        onContextMenu={(issue, anchor) => {
          const r = anchor.getBoundingClientRect();
          setMenu({ issue, x: r.left + 24, y: r.bottom });
        }}
        height="100%"
        notice={
          noSyntax ? (
            <Banner tone="info" data-testid="wiki-lint-nosyntax" actions={hasTab("rules") ? <Button size="sm" onClick={() => goTab("rules")}>{t.openRule}</Button> : undefined}>{t.noSyntax}</Banner>
          ) : undefined
        }
      />
    );
  }

  return (
    <div className="wiki-lint" data-testid="wiki-lint">
      <div className="wiki-lint-toolbar" role="group" aria-label={t.toolbar}>
        <Button size="sm" loading={checking} onClick={() => void recheck()}>{checking ? t.checking : t.recheck}</Button>
        {typeof generated === "number" ? <span className="app-muted" title={String(generated)}>{t.lastChecked(formatRelative(generated, now))}</span> : null}
        {typeof report?.pages === "number" ? <span className="app-muted">{t.pages(report.pages)}</span> : null}
      </div>
      <div className="wiki-lint-body">{body}</div>
      {menu === null || menuIssue === undefined ? null : (
        <AnchoredMenu
          x={menu.x}
          y={menu.y}
          label={t.menu}
          onClose={() => setMenu(null)}
          items={[
            { id: "open", label: t.openPage, disabled: menuIssue.path === undefined || menuIssue.path === null, onSelect: () => openIssue(menuIssue, lineOf(menuIssue)) },
            {
              id: "copy",
              label: t.copyPath,
              disabled: menuIssue.path === undefined || menuIssue.path === null,
              onSelect: () => {
                void navigator.clipboard?.writeText(menuIssue.path ?? "");
                toast({ tone: "success", text: t.copied });
              },
            },
            ...(menuRule !== null ? [{ id: "rule", label: t.openRule, onSelect: () => openRule(menuRule) }] : []),
          ]}
        />
      )}
    </div>
  );
}

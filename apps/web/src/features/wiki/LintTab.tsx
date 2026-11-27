/**
 * 점검 탭(screen-wiki §8): 서버 점검 결과(`GET …/lint`)를 표로 보이고 심각도·코드·페이지로 거른다(거르기는 주소 `sev`·`code`·`q`).
 * 행을 열면 그 페이지(+줄)로 간다. [다시 점검] = 다시 읽기(`scan`) 뒤 점검을 다시 받는다. 링크 문법이 없으면 링크 점검이 없다는 안내를 표 위에 둔다.
 * 점검 코드·규칙 id·메시지는 서버 값이고 이름·톤 표는 앱 표시 표(`WikiDisplay`)가 준다.
 */
import { useCallback, useState } from "react";
import { useNavigate } from "react-router";
import { Banner, Button, useToast } from "@agent-console/ui";
import { LintTable, issuePage, type LintFilter } from "@agent-console/wiki-view";
import type { WikiIssue } from "@agent-console/contracts/wiki";
import { useNow } from "../../app/useNow";
import { AnchoredMenu } from "./AnchoredMenu";
import { FailureBlock, ListSkeleton } from "./parts";
import { useWikiLint } from "./useWikiTabsApi";
import { useWikiSpace, useWikiSyntax } from "./useWikiApi";
import { SEVERITY_ORDER, WIKI_PARAMS } from "./wikiConfig";
import { wikiRulesPath } from "./wikiPaths";
import type { WikiTabProps } from "./wikiTabs";
import { localizeIssue } from "./wikiIssueText";
import { useServerText, useT } from "@agent-console/i18n";
import { useMaybeT } from "../../i18n/useMaybeT";
import { useWikiViewMessages } from "./useViewMessages";
import { useFormat } from "../../i18n";

const P = WIKI_PARAMS;

/** 코드 거르기 값은 점검 결과에 실제 있는 코드만 의미가 있으므로 그대로 쓴다. 주소 값을 거르기 상태로. */
function filterFromParams(params: URLSearchParams): Partial<LintFilter> {
  const sev = params.get(P.severity);
  return { severities: sev === null || sev === "" ? [] : sev.split(","), code: params.get(P.code) ?? "", page: params.get(P.query) ?? "" };
}

export function LintTab({ wikiId, view, ctx, display, params, setParams, goTab, hasTab, refresh }: WikiTabProps) {
  const fmt = useFormat();
  const wikiViewMessages = useWikiViewMessages();
  const t = useT("wiki");
  const server = useServerText();
  const tm = useMaybeT("wiki");
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
      const page = issuePage(issue);
      if (page === null) return;
      goTab("page", { [P.path]: page, ...(line === null ? {} : { [P.line]: String(line) }) });
    },
    [goTab],
  );
  const ruleOf = (issue: WikiIssue): string | null => {
    const id = issue.rule_id ?? issue.details?.["rule_id"];
    return typeof id === "string" && id !== "" ? id : null;
  };
  const lineOf = (issue: WikiIssue): number | null => {
    const v = issue.line ?? issue.details?.["line"];
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
      toast({ tone: "danger", text: e instanceof Error && e.message !== "" ? e.message : t("problem.generic") });
    } finally {
      setChecking(false);
    }
  };

  const report = lintQ.data;
  const issues = report?.issues ?? [];
  const generated = report?.generated_at;
  const skipped = report?.partial === true ? (report.skipped ?? []) : [];
  const enabledNames = (report?.enabled_checks ?? []).map((name) => display.codes?.[name]?.label ?? tm(`tab.lint.checkNames.${name}`) ?? name);
  const menuIssue = menu?.issue;
  const menuRule = menuIssue === undefined ? null : ruleOf(menuIssue);

  let body;
  if (lintQ.isPending) body = <ListSkeleton rows={8} />;
  else if (lintQ.isError || report === undefined) body = <FailureBlock error={lintQ.error} title={t("tab.lint.loadFailed")} onRetry={() => void lintQ.refetch()} />;
  else if (issues.length === 0 && noSyntax && lintRules === 0) {
    body = (
      <Banner tone="info" data-testid="wiki-lint-none-enabled" actions={hasTab("rules") ? <Button size="sm" onClick={() => goTab("rules")}>{t("tab.lint.openRule")}</Button> : undefined}>{t("tab.lint.noneEnabled")}</Banner>
    );
  } else {
    body = (
      <LintTable messages={wikiViewMessages} locale={fmt.language}
        issues={issues.map((i) => localizeIssue(i, server))}
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
            <Banner tone="info" data-testid="wiki-lint-nosyntax" actions={hasTab("rules") ? <Button size="sm" onClick={() => goTab("rules")}>{t("tab.lint.openRule")}</Button> : undefined}>{t("tab.lint.noSyntax")}</Banner>
          ) : undefined
        }
      />
    );
  }

  return (
    <div className="wiki-lint" data-testid="wiki-lint">
      <div className="wiki-lint-toolbar" role="group" aria-label={t("tab.lint.toolbar")}>
        <Button size="sm" loading={checking} onClick={() => void recheck()}>{checking ? t("tab.lint.checking") : t("tab.lint.recheck")}</Button>
        {typeof generated === "number" ? <span className="app-muted" title={String(generated)}>{t("tab.lint.lastChecked", { time: fmt.relative(generated, now) })}</span> : null}
        {typeof report?.pages === "number" ? <span className="app-muted">{t("tab.lint.pages", { n: report.pages })}</span> : null}
      </div>
      {report?.enabled_checks == null || enabledNames.length === 0 ? null : <p className="app-muted wiki-lint-enabled" data-testid="wiki-lint-enabled">{t("tab.lint.enabledChecks", { names: enabledNames.join(", ") })}</p>}
      {report?.partial !== true ? null : (
        <Banner tone="warning" data-testid="wiki-lint-partial">
          <span>{t("tab.lint.partial")}{skipped.length > 0 ? ` · ${t("tab.lint.partialCount", { count: skipped.length })}` : ""}</span>
          {skipped.length === 0 ? null : (
            <ul className="wiki-lint-skipped">
              {skipped.map((path) => (
                <li key={path}>
                  <button type="button" className="app-link-btn wiki-mono" aria-label={t("tab.lint.openSkipped", { path })} onClick={() => goTab("page", { [P.path]: path })}>{path}</button>
                </li>
              ))}
            </ul>
          )}
        </Banner>
      )}
      <div className="wiki-lint-body">{body}</div>
      {menu === null || menuIssue === undefined ? null : (
        <AnchoredMenu
          x={menu.x}
          y={menu.y}
          label={t("tab.lint.menu")}
          onClose={() => setMenu(null)}
          items={[
            { id: "open", label: t("tab.lint.openPage"), disabled: issuePage(menuIssue) === null, onSelect: () => openIssue(menuIssue, lineOf(menuIssue)) },
            {
              id: "copy",
              label: t("tab.lint.copyPath"),
              disabled: issuePage(menuIssue) === null,
              onSelect: () => {
                void navigator.clipboard?.writeText(issuePage(menuIssue) ?? "");
                toast({ tone: "success", text: t("tab.lint.copied") });
              },
            },
            ...(menuRule !== null ? [{ id: "rule", label: t("tab.lint.openRule"), onSelect: () => openRule(menuRule) }] : []),
          ]}
        />
      )}
    </div>
  );
}

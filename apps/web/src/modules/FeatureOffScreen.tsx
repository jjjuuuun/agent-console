import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { IconButton, Icon } from "@agent-console/ui";
import type { ModuleInfo } from "@agent-console/contracts";
import { messages as m } from "../app/messages";
import { ModuleStatusChip } from "./ModuleStatusChip";
import { MODULE_STATUS, worstSeverity, type Severity, type UnmetItem } from "./resolve";

const MAX_ITEMS = 4;
const MAX_MATCHES = 3;
const COPIED_MS = 1500;

export interface FeatureOffScreenProps {
  /** 화면 제목(라우트 `titleKey`를 푼 문구) */
  screenTitle: string;
  unmet: readonly UnmetItem[];
  /** [기능 목록 보기]가 가는 곳 */
  modulesHref: string;
  /** 이동할 수 있는 첫 화면(없으면 보조 버튼이 없다) */
  home?: { title: string; path: string } | undefined;
}

function reasonOf(mod: ModuleInfo): string | undefined {
  if (mod.reason !== undefined && mod.reason !== null && mod.reason !== "") return mod.reason;
  return (m.moduleStatusDefault as Record<string, string>)[mod.status];
}

/** 설치자가 서버 설정 파일에 붙여 넣을 수 있는 텍스트(꺼진 모듈 id를 끼운다). */
export function enableSnippet(ids: readonly string[]): string {
  return [
    m.moduleOff.howto.comment,
    "modules:",
    `  disabled: []   ${m.moduleOff.howto.removeFrom(ids.join(", "))}`,
    m.moduleOff.howto.orCli,
    ...ids.map((id) => `agent-console serve --enable-module ${id}`),
  ].join("\n");
}

function ModuleRow({ mod }: { mod: ModuleInfo }) {
  const reason = reasonOf(mod);
  return (
    <li className="app-off-module">
      <span className="app-off-line">
        <code className="app-wrap">{mod.id}</code>
        <ModuleStatusChip status={mod.status} />
      </span>
      {reason === undefined ? null : <span className="app-muted app-wrap">{reason}</span>}
    </li>
  );
}

function NeededItem({ item }: { item: UnmetItem }) {
  const shown = item.matches.slice(0, MAX_MATCHES);
  const rest = item.matches.length - shown.length;
  return (
    <li className="app-off-item">
      {item.by === "role" ? (
        <span className="app-off-line">
          <code className="app-wrap">{item.require}</code>
          <span className="app-muted">{m.moduleOff.roleMark}</span>
        </span>
      ) : null}
      {item.matches.length === 0 ? (
        <span className="app-off-line">
          {item.by === "module" ? <code className="app-wrap">{item.require}</code> : null}
          <span className="app-module-chip" data-module-status="unknown">{m.moduleOff.notListed}</span>
        </span>
      ) : (
        <ul className="app-off-modules" role="list">
          {shown.map((mod) => (
            <ModuleRow key={mod.id} mod={mod} />
          ))}
          {rest > 0 ? <li className="app-muted">{m.moduleOff.moreMatches(rest)}</li> : null}
        </ul>
      )}
    </li>
  );
}

function CopyBox({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const h = setTimeout(() => setCopied(false), COPIED_MS);
    return () => clearTimeout(h);
  }, [copied]);
  return (
    <div className="app-off-code">
      <pre>{text}</pre>
      <IconButton
        label={copied ? m.common.copied : m.common.copy}
        icon={<Icon name={copied ? "check" : "copy"} />}
        size="sm"
        onClick={() => {
          void navigator.clipboard?.writeText(text).then(() => setCopied(true), () => {});
        }}
      />
    </div>
  );
}

/**
 * 꺼진 기능 안내 화면. 라우트의 `requires` 중 만족하지 못한 항목과 그 모듈의 상태·이유를 그대로 보이고,
 * 켜는 방법은 안내만 한다(웹은 설정을 바꾸지 않는다). 모듈 id·역할 이름은 서버가 준 값을 그대로 쓴다.
 */
export function FeatureOffScreen({ screenTitle, unmet, modulesHref, home }: FeatureOffScreenProps) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  const [expanded, setExpanded] = useState(false);
  useEffect(() => headingRef.current?.focus(), []);

  const severity: Severity = worstSeverity(unmet) ?? "disabled";
  const shown = expanded ? unmet : unmet.slice(0, MAX_ITEMS);
  const disabledIds = [...new Set(unmet.flatMap((u) => u.matches.filter((x) => x.status === MODULE_STATUS.disabled).map((x) => x.id)))];
  const body = (m.moduleOff.body as Record<Severity, (screen: string) => string>)[severity](screenTitle);

  return (
    <div className="app-screen-frame" data-screen="feature-off" data-severity={severity}>
      <div className="app-off">
        <Icon name="module-disabled" size={32} />
        <h1 ref={headingRef} tabIndex={-1} className="app-off-title">
          {m.moduleOff.title[severity]}
        </h1>
        <p className="app-muted app-wrap">{body}</p>

        <section className="app-off-box" aria-label={m.moduleOff.needed}>
          <h2 className="app-off-box-title">{m.moduleOff.needed}</h2>
          <ul role="list" className="app-off-items">
            {shown.map((item) => (
              <NeededItem key={item.require} item={item} />
            ))}
          </ul>
          {!expanded && unmet.length > MAX_ITEMS ? (
            <div className="app-off-more">
              <span className="app-muted">{m.moduleOff.moreMatches(unmet.length - MAX_ITEMS)}</span>{" "}
              <button type="button" className="ac-btn" data-variant="ghost" data-size="sm" onClick={() => setExpanded(true)}>
                {m.moduleOff.showMore}
              </button>
            </div>
          ) : null}
        </section>

        {severity === "missing" ? <p className="app-wrap">{m.moduleOff.notInstalled}</p> : null}
        {severity === "disabled" && disabledIds.length > 0 ? (
          <section className="app-off-box" aria-label={m.moduleOff.howto.title}>
            <h2 className="app-off-box-title">{m.moduleOff.howto.title}</h2>
            <CopyBox text={enableSnippet(disabledIds)} />
          </section>
        ) : null}
        {severity === "unsatisfied" ? <p className="app-wrap">{m.moduleOff.howto.unsatisfied}</p> : null}
        {severity === "conflict" ? <p className="app-wrap">{m.moduleOff.howto.conflict}</p> : null}
        {severity === "failed" ? <p className="app-wrap">{m.moduleOff.howto.failed}</p> : null}

        {severity === "missing" ? null : <p className="app-muted app-off-note">{m.moduleOff.noChange}</p>}
        <div className="app-inline-actions">
          <Link to={modulesHref} className="ac-btn" data-variant="primary" data-size="md">
            {m.moduleOff.toModules}
          </Link>
          {home === undefined ? null : (
            <Link to={home.path} className="ac-btn" data-size="md">
              {m.moduleOff.goTo(home.title)}
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}

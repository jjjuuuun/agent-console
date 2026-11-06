import { KNOWN_WIKI_SYNTAX_SOURCES } from "@agent-console/contracts/constants";
import type { EffectiveWikiSyntax } from "@agent-console/contracts/wiki";
import { RulesSourceBadge, ToneChip } from "@agent-console/markdown-doc";
import type { ReactNode } from "react";
import { resolveDisplay, type WikiDisplay } from "./display";
import { formatMessage, resolveMessages } from "./messages";

export interface SyntaxValueTreeProps {
  /** 병합한 문법과 값마다 출처(`GET …/syntax`) */
  syntax: EffectiveWikiSyntax | null | undefined;
  display?: WikiDisplay;
  /** 최상위 키의 제목(스키마 `title`). 없으면 키 원문. */
  titles?: Readonly<Record<string, string>>;
  /** 출처가 규칙/설정/기본일 때의 [규칙 열기]·[설정에서 보기]. 출처 원문을 준다. */
  onOpenSource?: (source: string) => void;
  /** 문구 덮어쓰기 */
  messages?: Readonly<Record<string, string>>;
  className?: string;
}

/** JSON 포인터 한 조각 이스케이프 */
function esc(seg: string): string {
  return seg.replace(/~/g, "~0").replace(/\//g, "~1");
}

function Scalar({ v }: { v: unknown }): ReactNode {
  if (v === null || v === undefined) return <span className="ac-wk-muted">—</span>;
  if (typeof v === "string") return <span className="ac-wk-mono ac-wk-val" title={v}>{v === "" ? "\"\"" : v}</span>;
  return <span className="ac-wk-mono ac-wk-val">{String(v)}</span>;
}

/**
 * 유효 문법을 읽기 전용 값 트리로 보인다. 최상위 키마다 한 블록(제목 + 출처 배지), 객체·배열은 들여쓴 키-값, 문자열(패턴)은 mono.
 * 출처는 `sources`의 JSON 포인터(`/키`, 더 구체적인 포인터가 있으면 그 하위 항목에도 배지)이고 값은 서버 열린 문자열이다
 * (모르는 출처는 원문). 이 컴포넌트는 값을 편집하지 않는다.
 */
export function SyntaxValueTree({ syntax, display, titles, onOpenSource, messages, className }: SyntaxValueTreeProps) {
  const t = resolveMessages(messages);
  const value = (syntax?.syntax ?? {}) as Record<string, unknown>;
  const sources = syntax?.sources ?? {};
  const keys = Object.keys(value).filter((k) => value[k] !== null && value[k] !== undefined);
  const links = value["links"];
  const noLinks = syntax?.empty === true;

  const badgeFor = (source: string): ReactNode => {
    const rules = KNOWN_WIKI_SYNTAX_SOURCES.RULES_PREFIX;
    const d = resolveDisplay(display?.sources, source);
    const label = source.startsWith(rules) && !d.known ? formatMessage(t["syntax.source.rules"], { id: source.slice(rules.length) }) : d.label;
    return (
      <span className="ac-wk-inline">
        <RulesSourceBadge source={source} messages={{ [`source.${source}`]: label }} />
        {onOpenSource ? <button type="button" className="ac-wk-linkbtn" onClick={() => onOpenSource(source)}>{t["syntax.source.open"]}</button> : null}
      </span>
    );
  };

  const walk = (v: unknown, pointer: string, parentSource: string | undefined): ReactNode => {
    if (Array.isArray(v)) {
      if (v.length === 0) return <span className="ac-wk-muted">{t["syntax.emptyList"]}</span>;
      return (
        <ol className="ac-wk-vtree">
          {v.map((item, i) => {
            const p = `${pointer}/${i}`;
            const own = sources[p];
            return (
              <li key={p}>
                {own !== undefined && own !== parentSource ? <div className="ac-wk-vtree-badge">{badgeFor(own)}</div> : null}
                {walk(item, p, own ?? parentSource)}
              </li>
            );
          })}
        </ol>
      );
    }
    if (v !== null && typeof v === "object") {
      const entries = Object.entries(v as Record<string, unknown>).filter(([, x]) => x !== null && x !== undefined);
      if (entries.length === 0) return <span className="ac-wk-muted">{t["syntax.emptyList"]}</span>;
      return (
        <dl className="ac-wk-vtree">
          {entries.map(([k, x]) => {
            const p = `${pointer}/${esc(k)}`;
            const own = sources[p];
            const nested = x !== null && typeof x === "object";
            return (
              <div key={p} className="ac-wk-vtree-entry">
                <dt className="ac-wk-mono">{k}</dt>
                <dd>
                  {own !== undefined && own !== parentSource ? <span className="ac-wk-vtree-badge">{badgeFor(own)}</span> : null}
                  {nested ? walk(x, p, own ?? parentSource) : <Scalar v={x} />}
                </dd>
              </div>
            );
          })}
        </dl>
      );
    }
    return <Scalar v={v} />;
  };

  return (
    <div className={`ac-wk-root ac-wk-syntax${className ? ` ${className}` : ""}`}>
      {syntax && (noLinks || (Array.isArray(links) && links.length === 0)) ? (
        <div role="status"><ToneChip label={t["syntax.noLinks"] ?? ""} tone="warning" size="normal" /></div>
      ) : null}
      {keys.length === 0 ? <p className="ac-wk-muted" role="status">{t["syntax.empty"]}</p> : null}
      {keys.map((k) => {
        const pointer = `/${esc(k)}`;
        const src = sources[pointer];
        return (
          <section key={k} className="ac-wk-syntax-block" aria-label={titles?.[k] ?? k}>
            <header className="ac-wk-inline">
              <h4 className="ac-wk-grow">{titles?.[k] ?? k}</h4>
              {src !== undefined ? badgeFor(src) : null}
            </header>
            {walk(value[k], pointer, src)}
          </section>
        );
      })}
    </div>
  );
}

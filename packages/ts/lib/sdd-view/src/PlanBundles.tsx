import type { ParsedTask, TaskPlan } from "@agent-console/contracts/sdd";
import { formatMessage, resolveMessages } from "./messages";
import { planBundles } from "./plan";

export interface PlanBundlesProps {
  plan: TaskPlan;
  tasks: readonly ParsedTask[];
  onSelect?: (taskKey: string) => void;
  messages?: Readonly<Record<string, string>>;
  className?: string;
}

/** 병렬 묶음을 글로 보여 주는 목록(그래프의 글 대체). 묶음 = 서로 의존하지 않아 동시에 할 수 있는 작업들. */
export function PlanBundles({ plan, tasks, onSelect, messages, className }: PlanBundlesProps) {
  const text = resolveMessages(messages);
  const bundles = planBundles(plan, tasks);
  const cycles = plan.cycles ?? [];
  const critical = plan.critical_path ?? [];
  return (
    <section className={`ac-sdd-root ac-sdd-bundles${className ? ` ${className}` : ""}`} aria-label={text["plan.bundles"]}>
      {bundles.length === 0 ? (
        <p className="ac-sdd-muted" role="status">
          {text["plan.bundlesEmpty"]}
        </p>
      ) : (
        <ol className="ac-sdd-bundle-list">
          {bundles.map((b) => (
            <li key={b.index} className="ac-sdd-bundle">
              <p className="ac-sdd-bundle-head">
                <strong>{formatMessage(text["plan.bundle"], { n: b.index })}</strong> <span className="ac-sdd-muted">{formatMessage(text["plan.bundleCount"], { n: b.keys.length })}</span>
              </p>
              <ul role="list">
                {b.keys.map((key, i) => (
                  <li key={key}>
                    {onSelect ? (
                      <button type="button" className="ac-sdd-link" onClick={() => onSelect(key)}>
                        {b.titles[i]}
                      </button>
                    ) : (
                      b.titles[i]
                    )}
                    {critical.includes(key) ? <span className="ac-sdd-muted"> · {text["plan.critical"]}</span> : null}
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ol>
      )}
      {critical.length > 0 ? (
        <p className="ac-sdd-muted" title={text["plan.criticalHint"]}>
          {formatMessage(text["plan.criticalPath"], { n: critical.length })}
        </p>
      ) : null}
      {cycles.length > 0 ? (
        <div className="ac-sdd-banner" data-tone="warning" role="alert">
          <strong>{text["plan.cycles"]}</strong>
          <ul role="list">
            {cycles.map((c) => (
              <li key={c.join(">")} className="ac-sdd-mono">
                {formatMessage(text["plan.cycleLine"], { keys: c.join(" → ") })}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

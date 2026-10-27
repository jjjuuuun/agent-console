import type { ReactNode } from "react";
import { Button } from "./Button";
import { joinClass } from "./Status";

export interface StepGuideStep {
  id: string;
  /** 단계 이름(짧게). 예: "팀 만들기" */
  label: string;
  /** 단계 설명(선택, 한 줄) */
  hint?: ReactNode;
  /** 서버 데이터로 계산한 완료 여부(수동 체크 없음) */
  done: boolean;
  /** 이동 경로. `renderLink`가 링크로 그린다 */
  to?: string;
  /** 이동 대신 동작(둘 다 있으면 `onAction`이 우선) */
  onAction?: () => void;
  /** 버튼 글자(없으면 `messages.go`) */
  actionLabel?: string;
}

export interface StepGuideMessages {
  /** 목록 라벨 */
  stepsLabel: string;
  /** 단계 버튼 기본 글자 */
  go: string;
  /** 완료 단계의 스크린리더 글자 */
  done: string;
}

export interface StepGuideProps {
  steps: readonly StepGuideStep[];
  messages: StepGuideMessages;
  /** `to`를 링크로 그리는 함수(라우터를 모르는 패키지라 호출자가 준다). 없으면 `<a href>` */
  renderLink?: (props: { to: string; className: string; children: ReactNode; dataAttrs: Record<string, string> }) => ReactNode;
  /** 가로 3칸(넓은 곳) / 세로 목록 */
  layout?: "row" | "column";
  className?: string;
}

/**
 * 첫 단계 안내(표현 전용). 번호 있는 단계 목록이며 처음 미완료 단계만 강조(`data-current`)한다.
 * 단계 데이터·문구·이동은 모두 props다. 단계가 0개면 아무것도 그리지 않는다.
 */
export function StepGuide({ steps, messages, renderLink, layout = "column", className }: StepGuideProps) {
  if (steps.length === 0) return null;
  const currentIndex = steps.findIndex((s) => !s.done);
  return (
    <ol className={joinClass("ac-stepguide", className)} aria-label={messages.stepsLabel} data-layout={layout}>
      {steps.map((s, i) => {
        const label = s.actionLabel ?? messages.go;
        const cls = "ac-btn";
        const attrs = { "data-variant": i === currentIndex ? "primary" : "secondary", "data-size": "sm", "data-step-action": s.id };
        let action: ReactNode = null;
        if (!s.done) {
          if (s.onAction) action = <Button size="sm" variant={i === currentIndex ? "primary" : "secondary"} onClick={s.onAction} data-step-action={s.id}>{label}</Button>;
          else if (s.to !== undefined) {
            action = renderLink
              ? renderLink({ to: s.to, className: cls, children: label, dataAttrs: attrs })
              : <a className={cls} href={s.to} {...attrs}>{label}</a>;
          }
        }
        return (
          <li key={s.id} className="ac-stepguide-step" data-step={s.id} data-done={s.done ? "true" : "false"} data-current={i === currentIndex ? "true" : "false"} aria-current={i === currentIndex ? "step" : undefined}>
            <span className="ac-stepguide-num" aria-hidden="true">{s.done ? "✓" : i + 1}</span>
            <span className="ac-stepguide-text">
              <strong>{s.label}</strong>
              {s.hint ? <span className="ac-stepguide-hint">{s.hint}</span> : null}
              {s.done ? <span className="ac-sr-only">{messages.done}</span> : null}
            </span>
            {action}
          </li>
        );
      })}
    </ol>
  );
}

export interface QuickStartItem {
  id: string;
  title: string;
  description?: string;
  /** 왼쪽 36px 아이콘 타일에 넣을 노드(예: `<Icon name=.../>`). 없으면 타일을 그리지 않는다. */
  icon?: ReactNode;
  /** 배지 글자들(예: "체험") */
  badges?: readonly string[];
  /** 이 항목이 진행 중 */
  busy?: boolean;
}

export interface QuickStartRowProps {
  items: readonly QuickStartItem[];
  /** 줄 제목(예: "바로 시작") */
  title: string;
  startLabel: string;
  onStart: (id: string) => void;
  /** 다른 항목이 진행 중이면 나머지는 막는다 */
  disabled?: boolean;
  className?: string;
}

/** "한 번에 시작" 카드 줄(표현 전용). 항목이 0개면 아무것도 그리지 않는다. */
export function QuickStartRow({ items, title, startLabel, onStart, disabled, className }: QuickStartRowProps) {
  if (items.length === 0) return null;
  return (
    <section className={joinClass("ac-quickstart", className)} aria-label={title}>
      <h3 className="ac-quickstart-title">{title}</h3>
      <ul className="ac-quickstart-list">
        {items.map((it) => (
          <li key={it.id} className="ac-quickstart-card" data-quick-start={it.id}>
            {it.icon === undefined ? null : <span className="ac-quickstart-icon" aria-hidden="true">{it.icon}</span>}
            <div className="ac-quickstart-body">
              <strong className="ac-quickstart-name">{it.title}</strong>
              {(it.badges ?? []).map((b) => <span key={b} className="ac-quickstart-badge">{b}</span>)}
              {it.description ? <p className="ac-quickstart-desc">{it.description}</p> : null}
            </div>
            <Button size="sm" variant="primary" loading={it.busy === true} disabled={disabled === true && it.busy !== true} onClick={() => onStart(it.id)} aria-label={`${it.title} ${startLabel}`}>{startLabel}</Button>
          </li>
        ))}
      </ul>
    </section>
  );
}

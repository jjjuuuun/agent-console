/** 스펙 화면들이 같이 쓰는 작은 부품: 검색 칸·실패 블록·꺼짐 안내·스켈레톤·막힌 버튼. 데이터와 콜백은 props. */
import { useEffect, useId, useRef, useState, type ReactNode, type Ref } from "react";
import { Button, EmptyState, Icon, Menu, Popover, type MenuItemDef } from "@agent-console/ui";
import { ErrorBlock } from "../../app/ErrorBlock";
import { useDelayed } from "../../app/useDelayed";
import { isImeKeyEvent } from "../../lib/ime";
import { ROUTE_ROLES, routePath } from "../library";
import { SDD_LIMITS } from "./sddConfig";
import { classifySddError } from "./sddErrors";
import { sddMessages as m } from "./messages";

/** 입력이 멈춘 뒤 `onCommit`을 부르는 검색 칸. 한글 조합 중에는 보내지 않고, 밖에서 값이 바뀌면 따라간다. */
export function SearchBox({ value, onCommit, label, placeholder, inputRef, delayMs = SDD_LIMITS.searchDebounceMs }: { value: string; onCommit: (q: string) => void; label: string; placeholder?: string; inputRef?: Ref<HTMLInputElement>; delayMs?: number }) {
  const [text, setText] = useState(value);
  const [seen, setSeen] = useState(value);
  const composing = useRef(false);
  if (seen !== value) {
    setSeen(value);
    setText(value);
  }
  const latest = useRef(onCommit);
  useEffect(() => {
    latest.current = onCommit;
  });
  useEffect(() => {
    if (text === value) return;
    const timer = setTimeout(() => {
      if (!composing.current) latest.current(text);
    }, delayMs);
    return () => clearTimeout(timer);
  }, [text, value, delayMs]);
  return (
    <input
      ref={inputRef}
      type="search"
      role="searchbox"
      className="sdd-search"
      aria-label={label}
      placeholder={placeholder ?? label}
      value={text}
      onChange={(e) => setText(e.target.value)}
      onCompositionStart={() => (composing.current = true)}
      onCompositionEnd={(e) => {
        composing.current = false;
        setText(e.currentTarget.value);
      }}
      onKeyDown={(e) => {
        if (isImeKeyEvent(e.nativeEvent)) return;
        if (e.key === "Enter") latest.current(text);
      }}
    />
  );
}

/** 프로젝트 연동이 꺼져 본문 전체를 대신하는 안내(`sdd.spaces_unavailable`). 기능 모듈 화면으로 가는 링크는 설정이 있을 때만. */
export function UnavailableState() {
  const settings = routePath(ROUTE_ROLES.settings);
  return (
    <div className="sdd-state" data-testid="sdd-unavailable">
      <EmptyState
        icon={<Icon name="folder" size={40} />}
        title={m.unavailable.title}
        description={m.unavailable.body}
        action={settings === "/" ? undefined : <a className="app-link-btn" href={`${settings}#modules`}>{m.unavailable.openModules}</a>}
      />
    </div>
  );
}

/** 요청 실패를 종류별로 보인다: 연동 꺼짐은 안내, 스펙 없음·폴더 문제·그 밖은 오류 블록(+ 다시 시도). */
export function FailureBlock({ error, title, onRetry, backTo }: { error: unknown; title: string; onRetry?: () => void; backTo?: ReactNode }) {
  const failure = classifySddError(error, title);
  if (failure.kind === "unavailable") return <UnavailableState />;
  if (failure.kind === "notFound") return <ErrorBlock title={m.notFound}>{backTo}</ErrorBlock>;
  return <ErrorBlock title={title} message={failure.message} {...(onRetry === undefined ? {} : { onRetry, retryLabel: m.retry })} />;
}

/** 150ms 넘게 걸릴 때만 보이는 스켈레톤 행. */
export function ListSkeleton({ rows = 6 }: { rows?: number }) {
  const show = useDelayed(true, SDD_LIMITS.skeletonDelayMs);
  if (!show) return null;
  return (
    <div className="app-skeleton" role="status" aria-busy="true" aria-label={m.loading}>
      {Array.from({ length: rows }, (_, i) => <div key={i} className="app-skeleton-row" />)}
    </div>
  );
}

/** 막힌 버튼은 숨기지 않고 `aria-disabled` + 이유 + 툴팁이다. 눌러도 아무 일 없고 포커스는 유지한다. */
export function GuardedButton({ blockedReason, onClick, children, variant, size = "sm", ariaLabel }: { blockedReason: string | undefined; onClick: () => void; children: ReactNode; variant?: "primary" | "secondary"; size?: "sm" | "md"; ariaLabel?: string }) {
  const blocked = blockedReason !== undefined && blockedReason !== "";
  const reasonId = useId();
  return (
    <>
      <Button
        size={size}
        {...(variant === undefined ? {} : { variant })}
        aria-disabled={blocked || undefined}
        aria-describedby={blocked ? reasonId : undefined}
        {...(ariaLabel === undefined ? {} : { "aria-label": ariaLabel })}
        title={blocked ? blockedReason : undefined}
        onClick={() => {
          if (!blocked) onClick();
        }}
      >
        {children}
      </Button>
      {blocked ? <span id={reasonId} className="ac-sr-only">{blockedReason}</span> : null}
    </>
  );
}

/** 눌러서 여는 메뉴 버튼(`Popover` + `Menu`). 막힌 이유가 있으면 `aria-disabled`이고 열리지 않는다. 항목·라벨은 props다. */
export function MenuButton({ label, items, blockedReason, size = "sm", panelLabel, align = "end" }: { label: ReactNode; items: readonly MenuItemDef[]; blockedReason?: string | undefined; size?: "sm" | "md"; panelLabel: string; align?: "start" | "end" }) {
  const [open, setOpen] = useState(false);
  const blocked = blockedReason !== undefined && blockedReason !== "";
  return (
    <Popover
      open={open && !blocked}
      onOpenChange={(next) => setOpen(next && !blocked)}
      panelRole="menu"
      panelLabel={panelLabel}
      align={align}
      renderTrigger={(trigger) => (
        <Button size={size} {...trigger} aria-disabled={blocked || undefined} title={blocked ? blockedReason : undefined}>{label}</Button>
      )}
    >
      {({ close }) => <Menu items={items} onClose={close} />}
    </Popover>
  );
}

/** 여러 값을 고르는 거르기 버튼(팝오버 안 체크박스 목록). 고른 수가 버튼에 보인다. 선택 값은 제어형이다. */
export function MultiFilter({ label, options, selected, onChange }: { label: string; options: readonly { id: string; label: string }[]; selected: readonly string[]; onChange: (next: string[]) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <Popover
      open={open}
      onOpenChange={setOpen}
      panelRole="dialog"
      panelLabel={label}
      renderTrigger={(trigger) => (
        <Button size="sm" {...trigger}>{selected.length === 0 ? label : `${label} ${selected.length}`} ▾</Button>
      )}
    >
      <ul className="sdd-multi" aria-label={label}>
        {options.map((o) => (
          <li key={o.id}>
            <label className="ac-choice">
              <input type="checkbox" checked={selected.includes(o.id)} onChange={(e) => onChange(e.target.checked ? [...selected, o.id] : selected.filter((x) => x !== o.id))} />
              <span>{o.label}</span>
            </label>
          </li>
        ))}
      </ul>
    </Popover>
  );
}

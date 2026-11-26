import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { Spinner } from "@agent-console/ui";

/** 언어 선택지 한 줄(데이터). 이름·검색어는 호출자가 `Intl.DisplayNames`로 만들어 준다. */
export interface LanguageOption {
  code: string;
  /** 그 언어 자기 이름(`lang={code}`로 그린다) */
  name: string;
  /** 검색에 걸릴 다른 이름들(예: 현재 화면 언어로 쓴 이름) */
  aliases?: readonly string[];
  /** 기준 언어 문구를 다 가졌는가. false면 "일부만 번역됨" 표시 */
  complete: boolean;
  /** 빠진 문구 수(서버가 세어 줄 때) */
  missing?: number | null | undefined;
  /** 앱 묶음 밖의 출처 이름(없으면 비움) */
  sources: readonly string[];
}

/** 화면에 보이는 모든 문구(호출자가 현재 언어로 채운다). 함수형은 값이 섞이는 문구다. */
export interface LanguageSelectMessages {
  /** 그룹 이름(`aria-label`) */
  label: string;
  auto: string;
  /** "지금: 한국어" */
  autoNow: (name: string) => string;
  /** 브라우저 언어를 쓸 수 없어 다른 언어로 보일 때의 설명 */
  autoFallback: (browserCode: string, name: string) => string;
  partial: string;
  /** 부분 번역 툴팁: 빠진 문구가 보일 대체 언어 이름, 빠진 수(알면) */
  partialHint: (fallbackName: string, missing: number | null | undefined) => string;
  sources: (sources: readonly string[]) => string;
  unavailable: (code: string) => string;
  unavailableHelp: string;
  loading: string;
  search: string;
  /** 적용 중 스피너의 이름 */
  pending: string;
}

export interface LanguageSelectProps {
  options: readonly LanguageOption[];
  /** 지금 고른 값. `null` = 자동 */
  value: string | null;
  /** 자동 행의 부제 */
  autoHint: { resolvedName: string; note?: string | undefined };
  /** 부분 번역 툴팁에 쓸 대체 언어 이름 */
  fallbackName: string;
  /** 적용 중인 선택(`undefined` = 없음, `null` = 자동) */
  pending?: string | null | undefined;
  /** 목록에 없는 저장값(있으면 맨 끝에 선택된 비활성 행) */
  unavailableValue?: string | undefined;
  /** 서버 언어 목록을 아직 받는 중 */
  loading?: boolean;
  onChange: (next: string | null) => void;
  messages: LanguageSelectMessages;
  /** 이 개수 이하면 라디오 목록, 넘으면 팝오버 목록(기본 6) */
  inlineMax?: number;
  /** 이 개수 이상이면 팝오버에 검색 입력(기본 13) */
  searchMin?: number;
  id?: string;
}

/** 대소문자·악센트를 무시하고 부분 일치(한글은 그대로). */
const fold = (text: string): string => text.normalize("NFD").replace(/\p{M}/gu, "").toLocaleLowerCase();

const AUTO = "\u0000auto";
const keyOf = (value: string | null): string => (value === null ? AUTO : value);

/** 선택지 한 행의 가운데 내용: 이름 | 코드 | 부분 번역 배지 | 출처. */
function OptionBody({ option, messages, fallbackName }: { option: LanguageOption; messages: LanguageSelectMessages; fallbackName: string }) {
  const hint = option.complete ? undefined : messages.partialHint(fallbackName, option.missing);
  return (
    <span className="app-lang-body">
      <span className="app-lang-name ac-ellipsis" lang={option.code} title={option.name}>
        {option.name}
      </span>
      <span className="app-lang-code">{option.code}</span>
      {option.complete ? (
        <span />
      ) : (
        <span className="app-lang-partial" title={hint}>
          <span aria-hidden="true">ⓘ</span> {messages.partial}
          <span className="ac-sr-only"> — {hint}</span>
        </span>
      )}
      {option.sources.length === 0 ? (
        <span />
      ) : (
        <span className="app-lang-sources ac-ellipsis" title={messages.sources(option.sources)}>
          {messages.sources(option.sources)}
        </span>
      )}
    </span>
  );
}

/**
 * 화면 언어 고르기(표현 컴포넌트, screen-i18n §2). 선택지가 `inlineMax`개 이하면 라디오 목록, 그보다 많으면 팝오버 목록이다.
 * "자동"이 항상 첫 항목이다. 데이터와 콜백만 받는다(서버·저장소를 모른다).
 */
export function LanguageSelect({
  options,
  value,
  autoHint,
  fallbackName,
  pending,
  unavailableValue,
  loading = false,
  onChange,
  messages,
  inlineMax = 6,
  searchMin = 13,
  id,
}: LanguageSelectProps) {
  const autoId = useId();
  const shown = pending === undefined ? value : pending;
  const count = options.length + 1;
  const mode = count <= inlineMax ? "inline" : "popover";
  const unavailable = unavailableValue !== undefined && !options.some((o) => o.code === unavailableValue) ? unavailableValue : undefined;
  const chosen = unavailable !== undefined && shown === unavailable ? unavailable : shown;

  const autoSub = (
    <span className="app-lang-auto-sub">
      <span className="app-muted">{messages.autoNow(autoHint.resolvedName)}</span>
      {autoHint.note === undefined ? null : <span className="app-muted app-lang-note">{autoHint.note}</span>}
    </span>
  );

  const pendingMark = (key: string | null) =>
    pending !== undefined && keyOf(pending) === keyOf(key) ? <Spinner label={messages.pending} /> : null;

  return (
    <div className="app-lang" id={id} aria-busy={pending !== undefined || loading ? true : undefined}>
      {mode === "inline" ? (
        <InlineList
          options={options}
          chosen={chosen}
          unavailable={unavailable}
          autoId={autoId}
          autoSub={autoSub}
          pendingMark={pendingMark}
          onChange={onChange}
          messages={messages}
          fallbackName={fallbackName}
        />
      ) : (
        <PopoverList
          options={options}
          chosen={chosen}
          unavailable={unavailable}
          autoSub={autoSub}
          autoName={messages.auto}
          pendingMark={pendingMark}
          onChange={onChange}
          messages={messages}
          fallbackName={fallbackName}
          searchable={count >= searchMin}
        />
      )}
      {unavailable === undefined ? null : (
        <p className="app-muted app-lang-note" role="status">
          {messages.unavailableHelp}
        </p>
      )}
      {loading ? (
        <p className="app-muted app-lang-loading" role="status">
          <Spinner /> {messages.loading}
        </p>
      ) : null}
    </div>
  );
}

interface ListProps {
  options: readonly LanguageOption[];
  chosen: string | null;
  unavailable: string | undefined;
  autoSub: ReactNode;
  pendingMark: (key: string | null) => ReactNode;
  onChange: (next: string | null) => void;
  messages: LanguageSelectMessages;
  fallbackName: string;
}

/** 라디오 목록. 화살표 키는 네이티브 라디오 그룹이 처리하고, Home·End만 더한다. */
function InlineList({ options, chosen, unavailable, autoId, autoSub, pendingMark, onChange, messages, fallbackName }: ListProps & { autoId: string }) {
  const group = useRef<HTMLDivElement>(null);
  const name = `lang-${autoId}`;
  const onKey = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "Home" && event.key !== "End") return;
    const radios = Array.from(group.current?.querySelectorAll<HTMLInputElement>('input[type="radio"]:not(:disabled)') ?? []);
    const target = event.key === "Home" ? radios[0] : radios[radios.length - 1];
    if (target === undefined) return;
    event.preventDefault();
    target.focus();
    target.click();
  };
  return (
    <div ref={group} role="radiogroup" aria-label={messages.label} className="app-lang-list" onKeyDown={onKey}>
      <label className="app-lang-row app-lang-row-auto">
        <input type="radio" name={name} value={AUTO} checked={chosen === null} onChange={() => onChange(null)} />
        <span className="app-lang-auto">
          <span className="app-lang-name">{messages.auto}</span>
          {autoSub}
        </span>
        {pendingMark(null)}
      </label>
      {options.map((option) => (
        <label key={option.code} className="app-lang-row">
          <input type="radio" name={name} value={option.code} checked={chosen === option.code} onChange={() => onChange(option.code)} />
          <OptionBody option={option} messages={messages} fallbackName={fallbackName} />
          {pendingMark(option.code)}
        </label>
      ))}
      {unavailable === undefined ? null : (
        <label className="app-lang-row" data-disabled="true">
          <input type="radio" name={name} value={unavailable} checked disabled readOnly />
          <span className="app-lang-name ac-ellipsis">{messages.unavailable(unavailable)}</span>
        </label>
      )}
    </div>
  );
}

/** 팝오버 목록: 트리거 버튼 + `listbox`. 선택지가 많으면 검색 입력을 둔다(조합 중 Enter는 무시). */
function PopoverList({
  options,
  chosen,
  unavailable,
  autoSub,
  autoName,
  pendingMark,
  onChange,
  messages,
  fallbackName,
  searchable,
}: ListProps & { autoName: string; searchable: boolean }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const trigger = useRef<HTMLButtonElement>(null);
  const root = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const listId = useId();
  const items = useMemo(() => {
    const needle = fold(query.trim());
    const rows: { key: string | null; label: string; option?: LanguageOption }[] = [{ key: null, label: autoName }];
    for (const option of options) rows.push({ key: option.code, label: option.name, option });
    return needle === ""
      ? rows
      : rows.filter((row) => row.key === null || [row.label, row.option?.code ?? "", ...(row.option?.aliases ?? [])].some((text) => fold(text).includes(needle)));
  }, [options, query, autoName]);

  const close = (focusTrigger: boolean) => {
    setOpen(false);
    setQuery("");
    if (focusTrigger) trigger.current?.focus();
  };
  const pick = (key: string | null) => {
    close(true);
    onChange(key);
  };

  // 바깥을 누르면 닫는다. 열릴 때 포커스를 목록(또는 검색 입력)으로 옮긴다.
  useEffect(() => {
    if (!open) return;
    (searchable ? searchRef.current : listRef.current)?.focus();
    const onDown = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) {
        setOpen(false);
        setQuery("");
      }
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open, searchable]);
  const activeIndex = Math.min(active, Math.max(items.length - 1, 0));
  const toggle = () => {
    if (!open) {
      const at = items.findIndex((row) => row.key === chosen);
      setActive(at < 0 ? 0 : at); // 열 때 선택된 행에서 시작
    }
    setOpen(!open);
  };

  const onKey = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      close(true);
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive(Math.min(activeIndex + 1, items.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive(Math.max(activeIndex - 1, 0));
    } else if (event.key === "Home" && !searchable) {
      event.preventDefault();
      setActive(0);
    } else if (event.key === "End" && !searchable) {
      event.preventDefault();
      setActive(items.length - 1);
    } else if (event.key === "Enter") {
      // 한글 조합 중의 Enter는 조합을 끝낼 뿐이다.
      if (event.nativeEvent.isComposing) return;
      event.preventDefault();
      const row = items[activeIndex];
      if (row !== undefined) pick(row.key);
    } else if (!searchable && event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
      const at = items.findIndex((row, i) => i > activeIndex && fold(row.label).startsWith(fold(event.key)));
      const first = at >= 0 ? at : items.findIndex((row) => fold(row.label).startsWith(fold(event.key)));
      if (first >= 0) setActive(first);
    }
  };

  const current = chosen === null ? undefined : options.find((o) => o.code === chosen);
  const triggerLabel = chosen === null ? autoName : current !== undefined ? current.name : messages.unavailable(chosen);
  const optionId = (index: number) => `${listId}-o${index}`;

  return (
    <div ref={root} className="app-lang-pop" onKeyDown={open ? onKey : undefined}>
      <button
        ref={trigger}
        type="button"
        className="ac-btn app-lang-trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        aria-label={`${messages.label}: ${triggerLabel}`}
        onClick={toggle}
        onKeyDown={(event) => {
          if (!open && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
            event.preventDefault();
            toggle();
          }
        }}
      >
        <span className="app-lang-name ac-ellipsis" {...(current === undefined ? {} : { lang: current.code })}>
          {triggerLabel}
        </span>
        {current === undefined ? null : <span className="app-lang-code">{current.code}</span>}
        <span aria-hidden="true">▾</span>
      </button>
      {chosen === null ? <div className="app-lang-auto-line">{autoSub}</div> : null}
      {open ? (
        <div className="ac-popover app-lang-panel" data-align="start">
          {searchable ? (
            <input
              ref={searchRef}
              type="search"
              className="ac-input app-lang-search"
              aria-label={messages.search}
              placeholder={messages.search}
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setActive(0);
              }}
            />
          ) : null}
          <ul
            id={listId}
            role="listbox"
            aria-label={messages.label}
            aria-activedescendant={items[activeIndex] === undefined ? undefined : optionId(activeIndex)}
            tabIndex={searchable ? -1 : 0}
            className="app-lang-listbox"
            ref={listRef}
          >
            {items.map((row, index) => (
              <li
                key={keyOf(row.key)}
                id={optionId(index)}
                role="option"
                aria-selected={chosen === row.key}
                data-active={index === activeIndex ? "true" : undefined}
                className="app-lang-option"
                onMouseEnter={() => setActive(index)}
                onClick={() => pick(row.key)}
              >
                {row.option === undefined ? (
                  <span className="app-lang-name ac-ellipsis">{row.label}</span>
                ) : (
                  <OptionBody option={row.option} messages={messages} fallbackName={fallbackName} />
                )}
                {pendingMark(row.key)}
              </li>
            ))}
            {unavailable === undefined ? null : (
              <li role="option" aria-selected="true" aria-disabled="true" className="app-lang-option" data-disabled="true">
                <span className="app-lang-name ac-ellipsis">{messages.unavailable(unavailable)}</span>
              </li>
            )}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

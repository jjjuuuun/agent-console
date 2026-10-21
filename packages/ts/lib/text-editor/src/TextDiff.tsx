import { goToNextChunk, goToPreviousChunk, MergeView, unifiedMergeView } from "@codemirror/merge";
import { EditorState, type Extension } from "@codemirror/state";
import { EditorView, keymap, lineNumbers } from "@codemirror/view";
import { useEffect, useRef, useState } from "react";
import { resolveLanguage } from "./languages";
import { editorHighlight, editorTheme } from "./theme";

/** 비교 보기 방식. `auto`는 폭이 `unifiedBelow`px 미만이면 통합, 아니면 나란히. */
export type TextDiffMode = "split" | "unified" | "auto";

export interface TextDiffMessages {
  /** 접힌 구간 안내. `$`는 줄 수로 바뀐다. 예: "변경 없는 $줄 — 펼치기" */
  unchangedLines: string;
  /** 도구 줄의 보기 전환 라벨 */
  split: string;
  unified: string;
  /** 도구 줄 접근성 이름 */
  toolbar: string;
}

export interface TextDiffProps {
  /** 이전(왼쪽) 내용 */
  before: string;
  /** 이후(오른쪽) 내용 */
  after: string;
  /** `markdown` | `html` | `json` | `text`. 모르는 값은 text. */
  language?: string;
  /** 접근성 이름(필수) */
  ariaLabel: string;
  /** 기본 `auto` */
  mode?: TextDiffMode;
  /** `auto`에서 통합 보기로 바꾸는 폭(px). 기본 900 */
  unifiedBelow?: number;
  /** 변경 없는 구간을 접을 때 남기는 앞뒤 줄 수. 기본 3. 0 미만이면 접지 않는다 */
  context?: number;
  /** 보기 전환 버튼을 보인다. 기본 true */
  showToolbar?: boolean;
  /** 보기 방식이 바뀔 때(전환 버튼 포함) 알린다 */
  onModeChange?: (mode: "split" | "unified") => void;
  /** px. 기본 360(넘치면 스크롤) */
  height?: number;
  messages?: Partial<TextDiffMessages>;
  className?: string;
}

const DEFAULT_MESSAGES: TextDiffMessages = {
  unchangedLines: "$ unchanged lines",
  split: "Side by side",
  unified: "Unified",
  toolbar: "Diff view",
};

const chunkKeys = keymap.of([
  { key: "F3", run: goToNextChunk, preventDefault: true },
  { key: "Shift-F3", run: goToPreviousChunk, preventDefault: true },
]);

function sideExtensions(language: string | undefined, label: string, phrases: Extension): Extension[] {
  return [
    lineNumbers(),
    EditorState.readOnly.of(true),
    EditorView.editable.of(false),
    EditorView.lineWrapping,
    editorTheme,
    editorHighlight,
    resolveLanguage(language),
    EditorView.contentAttributes.of({ "aria-label": label, "aria-readonly": "true", tabindex: "0" }),
    chunkKeys,
    phrases,
  ];
}

/**
 * 읽기 전용 텍스트 비교(`@codemirror/merge`). 나란히/통합 보기, 변경 없는 구간 접기, `F3`/`Shift+F3`로 다음/이전 변경 블록.
 * 도메인·저장·API를 모른다(두 문자열만 받는다). 색은 `--ac-*` 토큰, 변경 표시는 색 외에 gutter 막대·밑줄이 함께 나온다.
 */
export function TextDiff({
  before,
  after,
  language,
  ariaLabel,
  mode = "auto",
  unifiedBelow = 900,
  context = 3,
  showToolbar = true,
  onModeChange,
  height = 360,
  messages,
  className,
}: TextDiffProps) {
  const text = { ...DEFAULT_MESSAGES, ...messages };
  const host = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState<number | null>(null);
  const [picked, setPicked] = useState<{ forMode: TextDiffMode; value: "split" | "unified" } | null>(null);
  const notify = useRef(onModeChange);
  useEffect(() => {
    notify.current = onModeChange;
  });

  // 폭 측정(auto 전용). 측정 전/불가(0)면 나란히로 시작한다.
  useEffect(() => {
    const el = host.current;
    if (!el) return;
    setWidth(el.clientWidth);
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width;
      if (w !== undefined) setWidth(w);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const autoMode: "split" | "unified" = width !== null && width > 0 && width < unifiedBelow ? "unified" : "split";
  // 사용자가 전환 버튼으로 고른 값은 `mode` prop이 그대로인 동안만 유지한다(prop이 바뀌면 prop을 따른다).
  const forced = picked !== null && picked.forMode === mode ? picked.value : mode === "auto" ? null : mode;
  const effective = forced ?? autoMode;

  useEffect(() => {
    notify.current?.(effective);
  }, [effective]);

  useEffect(() => {
    const parent = host.current;
    if (!parent) return;
    const collapse = context >= 0 ? { margin: context, minSize: Math.max(4, context + 1) } : undefined;
    const phrases = EditorState.phrases.of({ "$ unchanged lines": text.unchangedLines });
    let destroy: () => void;
    if (effective === "split") {
      const view = new MergeView({
        a: { doc: before, extensions: sideExtensions(language, `${ariaLabel} (before)`, phrases) },
        b: { doc: after, extensions: sideExtensions(language, `${ariaLabel} (after)`, phrases) },
        parent,
        gutter: true,
        highlightChanges: true,
        ...(collapse ? { collapseUnchanged: collapse } : {}),
      });
      destroy = () => view.destroy();
    } else {
      const view = new EditorView({
        parent,
        state: EditorState.create({
          doc: after,
          extensions: [
            ...sideExtensions(language, ariaLabel, phrases),
            unifiedMergeView({
              original: before,
              mergeControls: false,
              gutter: true,
              highlightChanges: true,
              ...(collapse ? { collapseUnchanged: collapse } : {}),
            }),
          ],
        }),
      });
      destroy = () => view.destroy();
    }
    return destroy;
    // 메시지 객체는 매 렌더 새로 만들어지므로 문자열만 의존한다.
  }, [before, after, language, ariaLabel, effective, context, text.unchangedLines]);

  // 접힌 구간("변경 없는 N줄")은 라이브러리가 클릭 전용 div로 그린다. 키보드로도 펼치도록 버튼 역할·탭 정지·Enter/Space를 입힌다.
  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const enhance = () => {
      for (const n of el.querySelectorAll<HTMLElement>(".cm-collapsedLines")) {
        if (n.getAttribute("role") !== "button") {
          n.setAttribute("role", "button");
          n.tabIndex = 0;
        }
      }
    };
    enhance();
    const mo = new MutationObserver(enhance);
    mo.observe(el, { childList: true, subtree: true });
    const onKey = (e: KeyboardEvent) => {
      const t = e.target;
      if (!(t instanceof HTMLElement) || !t.classList.contains("cm-collapsedLines")) return;
      if (e.key !== "Enter" && e.key !== " ") return;
      e.preventDefault();
      e.stopPropagation();
      t.click();
      // 펼치면 그 자리가 사라지므로 포커스를 본문으로 옮겨 잃지 않게 한다.
      el.querySelector<HTMLElement>(".cm-content")?.focus();
    };
    el.addEventListener("keydown", onKey, true);
    return () => {
      mo.disconnect();
      el.removeEventListener("keydown", onKey, true);
    };
  }, []);

  const choose = (next: "split" | "unified") => setPicked({ forMode: mode, value: next });

  return (
    <div className={className} data-ac-diff={effective}>
      {showToolbar ? (
        <div role="group" aria-label={text.toolbar} className="ac-textdiff-toolbar" style={{ display: "flex", gap: 4, marginBottom: 4 }}>
          {(["split", "unified"] as const).map((m) => (
            <button
              key={m}
              type="button"
              aria-pressed={effective === m}
              className="ac-btn"
              data-variant={effective === m ? "primary" : "secondary"}
              data-size="sm"
              onClick={() => choose(m)}
            >
              <span className="ac-btn-label">{text[m]}</span>
            </button>
          ))}
        </div>
      ) : null}
      <div
        ref={host}
        data-ac-editable=""
        style={{ height, overflow: "auto", border: "1px solid var(--ac-border, #2e3541)", borderRadius: "var(--ac-radius-md, 6px)", background: "var(--ac-surface-1, #161a20)" }}
      />
    </div>
  );
}

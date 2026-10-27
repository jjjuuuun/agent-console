import { defaultKeymap, history, historyKeymap, indentWithTab } from "@codemirror/commands";
import { indentUnit } from "@codemirror/language";
import { Annotation, Compartment, EditorState, type Extension } from "@codemirror/state";
import { EditorView, drawSelection, highlightActiveLine, highlightActiveLineGutter, keymap, lineNumbers } from "@codemirror/view";
import { useEffect, useImperativeHandle, useMemo, useRef, type Ref } from "react";
import { byteLength, jsonParseError, resolveLanguage } from "./languages";
import { editorHighlight, editorTheme } from "./theme";

export interface TextEditorStatus {
  /** 1부터 */
  line: number;
  /** 1부터 */
  col: number;
  chars: number;
  /** language가 json일 때만. 편집을 막지 않는다. */
  parseError?: string;
}

/** `handleRef`로 받는 명령형 핸들. */
export interface TextEditorHandle {
  /** IME 조합 중인지(compositionstart~compositionend). */
  isComposing: () => boolean;
}

export interface TextEditorMessages {
  /** `maxBytes` 초과로 읽기 전용일 때 편집기에 붙는 설명(aria-description). */
  tooLarge: string;
}

export interface TextEditorProps {
  value: string;
  /** 사용자 편집(IME 조합 중 포함)만 호출한다. `value` prop 반영은 호출하지 않는다. */
  onChange?: (value: string) => void;
  /** `markdown` | `html` | `json` | `text`. 모르는 값은 text. */
  language?: string;
  readOnly?: boolean;
  /** 기본 true */
  lineWrap?: boolean;
  /** 접근성 이름(필수) */
  ariaLabel: string;
  /** Ctrl+S / Cmd+S (편집기 포커스, IME 조합 중에는 무시) */
  onSave?: () => void;
  /** UTF-8 바이트 상한. 초과하면 읽기 전용이 되고 `onTooLarge(bytes)`를 알린다. */
  maxBytes?: number;
  onTooLarge?: (bytes: number) => void;
  onStatus?: (status: TextEditorStatus) => void;
  /** IME 조합이 시작되면 true, 끝나면 false로 알린다(상태가 바뀔 때만). 조합 중 검사·저장을 미루는 데 쓴다. */
  onCompositionChange?: (composing: boolean) => void;
  /** 명령형 핸들(`isComposing()`). */
  handleRef?: Ref<TextEditorHandle>;
  /** px 또는 'fill'(부모 높이를 채움). 기본 'fill' */
  height?: number | "fill";
  messages?: Partial<TextEditorMessages>;
  className?: string;
}

const DEFAULT_MESSAGES: TextEditorMessages = { tooLarge: "" };
const external = Annotation.define<boolean>();

function computeStatus(state: EditorState, isJson: boolean): TextEditorStatus {
  const head = state.selection.main.head;
  const line = state.doc.lineAt(head);
  const status: TextEditorStatus = { line: line.number, col: head - line.from + 1, chars: state.doc.length };
  if (isJson) {
    const error = jsonParseError(state.doc.toString());
    if (error !== undefined) status.parseError = error;
  }
  return status;
}

/**
 * CodeMirror 6 기반 텍스트 편집기(제어형). 도메인·저장을 모른다.
 * 자동 완성·자동 괄호는 켜지 않는다(한글 IME 조합과 충돌 방지). 탭 키는 공백 2칸 들여쓰기이며 Esc 후 Tab으로 빠져나간다.
 */
export function TextEditor({
  value,
  onChange,
  language,
  readOnly = false,
  lineWrap = true,
  ariaLabel,
  onSave,
  maxBytes,
  onTooLarge,
  onStatus,
  onCompositionChange,
  handleRef,
  height = "fill",
  messages,
  className,
}: TextEditorProps) {
  const host = useRef<HTMLDivElement>(null);
  const view = useRef<EditorView | null>(null);
  const compartments = useRef({
    language: new Compartment(),
    editable: new Compartment(),
    wrap: new Compartment(),
    label: new Compartment(),
  });
  // 콜백은 ref로 들고 있어 편집기를 다시 만들지 않는다.
  const handlers = useRef({ onChange, onSave, onStatus, onTooLarge, onCompositionChange, language });
  useEffect(() => {
    handlers.current = { onChange, onSave, onStatus, onTooLarge, onCompositionChange, language };
  });
  const composing = useRef(false);
  const setComposing = (next: boolean) => {
    if (composing.current === next) return;
    composing.current = next;
    handlers.current.onCompositionChange?.(next);
  };
  useImperativeHandle(handleRef, () => ({ isComposing: () => composing.current }), []);

  const text = { ...DEFAULT_MESSAGES, ...messages };
  const tooLarge = maxBytes !== undefined && byteLength(value) > maxBytes;
  const locked = readOnly || tooLarge;

  const labelExt = useMemo<Extension>(
    () =>
      EditorView.contentAttributes.of({
        "aria-label": ariaLabel,
        ...(tooLarge && text.tooLarge ? { "aria-description": text.tooLarge } : {}),
        "data-ac-editable": "",
      }),
    [ariaLabel, tooLarge, text.tooLarge],
  );

  // 최초 생성 (value 이후 변경은 아래 효과들이 반영)
  useEffect(() => {
    const c = compartments.current;
    const state = EditorState.create({
      doc: value,
      extensions: [
        lineNumbers(),
        highlightActiveLine(),
        highlightActiveLineGutter(),
        drawSelection(),
        history(),
        EditorState.tabSize.of(2),
        indentUnit.of("  "),
        EditorView.domEventHandlers({
          compositionstart: () => {
            setComposing(true);
            return false;
          },
          compositionend: () => {
            setComposing(false);
            return false;
          },
          keydown: (event, v) => {
            if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== "s") return false;
            // IME 조합 중에는 단축키 처리를 하지 않는다.
            if (v.composing || event.isComposing || event.keyCode === 229) return false;
            const save = handlers.current.onSave;
            if (!save) return false;
            event.preventDefault();
            save();
            return true;
          },
        }),
        keymap.of([
          indentWithTab,
          ...defaultKeymap,
          ...historyKeymap,
        ]),
        editorTheme,
        editorHighlight,
        c.language.of(resolveLanguage(language)),
        c.editable.of([EditorView.editable.of(!locked), EditorState.readOnly.of(locked)]),
        c.wrap.of(lineWrap ? EditorView.lineWrapping : []),
        c.label.of(labelExt),
        EditorView.updateListener.of((update) => {
          if (update.docChanged && !update.transactions.some((tr) => tr.annotation(external))) {
            handlers.current.onChange?.(update.state.doc.toString());
          }
          if (update.docChanged || update.selectionSet) {
            handlers.current.onStatus?.(computeStatus(update.state, handlers.current.language === "json"));
          }
        }),
      ],
    });
    const v = new EditorView({ state, parent: host.current! });
    view.current = v;
    handlers.current.onStatus?.(computeStatus(v.state, language === "json"));
    return () => {
      composing.current = false;
      v.destroy();
      view.current = null;
    };
    // 편집기는 한 번만 만든다. 이후 prop 변화는 아래 효과가 compartment로 반영한다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 제어형 value 동기화: 같은 값이면 건드리지 않아 커서·IME 조합을 보존한다.
  useEffect(() => {
    const v = view.current;
    if (!v) return;
    const current = v.state.doc.toString();
    if (current === value) return;
    v.dispatch({ changes: { from: 0, to: current.length, insert: value }, annotations: external.of(true) });
  }, [value]);

  useEffect(() => {
    view.current?.dispatch({ effects: compartments.current.language.reconfigure(resolveLanguage(language)) });
    const v = view.current;
    if (v) onStatus?.(computeStatus(v.state, language === "json"));
    // onStatus는 ref 경유로 최신을 쓰므로 의존하지 않는다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [language]);

  useEffect(() => {
    view.current?.dispatch({
      effects: compartments.current.editable.reconfigure([EditorView.editable.of(!locked), EditorState.readOnly.of(locked)]),
    });
  }, [locked]);

  useEffect(() => {
    view.current?.dispatch({ effects: compartments.current.wrap.reconfigure(lineWrap ? EditorView.lineWrapping : []) });
  }, [lineWrap]);

  useEffect(() => {
    view.current?.dispatch({ effects: compartments.current.label.reconfigure(labelExt) });
  }, [labelExt]);

  const notifiedLarge = useRef(false);
  useEffect(() => {
    if (tooLarge && !notifiedLarge.current) handlers.current.onTooLarge?.(byteLength(value));
    notifiedLarge.current = tooLarge;
  }, [tooLarge, value]);

  return (
    <div
      ref={host}
      className={className}
      style={height === "fill" ? { height: "100%", display: "flex", flexDirection: "column", minHeight: 0 } : { height }}
      data-ac-editable=""
      data-language={language ?? "text"}
    />
  );
}

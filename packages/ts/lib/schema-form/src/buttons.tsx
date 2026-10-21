import type { IconButtonProps } from "@rjsf/utils";
import type { ButtonHTMLAttributes } from "react";
import type { SchemaFormMessages } from "./types";

/** rjsf가 넘기는 아이콘 버튼 props 중 DOM에 내리면 안 되는 것을 제외한다. */
function domProps(p: IconButtonProps): ButtonHTMLAttributes<HTMLButtonElement> {
  const { icon: _i, iconType: _t, uiSchema: _u, registry: _r, className, ...rest } = p as IconButtonProps & { className?: string };
  void _i; void _t; void _u; void _r;
  return { ...(rest as ButtonHTMLAttributes<HTMLButtonElement>), className: ["ac-sf-iconbtn", className].filter(Boolean).join(" ") };
}

function make(glyph: string, label: (m: SchemaFormMessages) => string, m: SchemaFormMessages, showText = false) {
  return function SchemaFormButton(props: IconButtonProps) {
    const text = label(m);
    return (
      <button type="button" {...domProps(props)} aria-label={text} title={text}>
        <span aria-hidden="true">{glyph}</span>
        {showText ? <span className="ac-sf-iconbtn-text">{text}</span> : null}
      </button>
    );
  };
}

/** rjsf 기본 버튼은 glyphicon 폰트에 의존하므로, 인라인 문자 아이콘 + 한국어 aria-label/title 버튼으로 교체한다. */
export function buttonTemplates(m: SchemaFormMessages) {
  return {
    AddButton: make("＋", (x) => x.addItem, m, true),
    RemoveButton: make("✕", (x) => x.removeItem, m),
    MoveUpButton: make("↑", (x) => x.moveUp, m),
    MoveDownButton: make("↓", (x) => x.moveDown, m),
    CopyButton: make("⧉", (x) => x.copyItem, m),
  };
}

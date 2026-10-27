import { Fragment, type ReactNode } from "react";

const TOKEN = /`([^`]+)`|\*\*([^*]+)\*\*/g;

/** 짧은 인라인 마크다운(`코드`, **굵게**)만 React 노드로 바꾼다. HTML은 해석하지 않고 글자로 둔다. */
export function parseInlineMarkdown(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  let i = 0;
  for (const m of text.matchAll(TOKEN)) {
    const at = m.index ?? 0;
    if (at > last) out.push(text.slice(last, at));
    out.push(m[1] !== undefined ? <code key={i++}>{m[1]}</code> : <strong key={i++}>{m[2]}</strong>);
    last = at + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

/** 마크다운 기호를 뺀 평문(title·aria용). */
export function stripInlineMarkdown(text: string): string {
  return text.replace(TOKEN, (_, a: string | undefined, b: string | undefined) => a ?? b ?? "");
}

/** 스키마·서버 설명 문자열용 인라인 렌더러. 코드·굵게만 그리고 나머지는 평문이다. */
export function InlineMarkdown({ text }: { text: string }) {
  return <Fragment>{parseInlineMarkdown(text)}</Fragment>;
}

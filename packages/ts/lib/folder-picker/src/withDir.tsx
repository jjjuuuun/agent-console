import type { ReactNode } from "react";

/** 문구의 `{dir}` 자리를 고정폭 글자(`code`)로 바꿔 그린다. */
export function withDir(template: string, dir: string): ReactNode {
  const parts = template.split("{dir}");
  return parts.flatMap((part, i) => (i === 0 ? [part] : [<code key={i} className="ac-fp-code">{dir}</code>, part]));
}

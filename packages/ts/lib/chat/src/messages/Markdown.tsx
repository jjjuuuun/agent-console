import { Children, isValidElement, useState, type ReactElement, type ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { s } from "../shared/styles";

export type MarkdownMessages = { copy: string; copied: string };
export const defaultMarkdownMessages: MarkdownMessages = { copy: "복사", copied: "복사됨" };

export interface MarkdownProps {
  text: string;
  /** 스트리밍 중이면 닫히지 않은 코드 펜스를 코드 블록으로 본다. */
  streaming?: boolean;
  /** 코드 복사 동작을 바꾼다. 없으면 `navigator.clipboard`. */
  onCopyText?: (text: string) => void;
  messages?: Partial<MarkdownMessages>;
}

/** 열린 채 끝난 코드 펜스(```)를 닫아 준다. 줄 맨 앞의 펜스만 센다. */
export function closeOpenFence(text: string): string {
  let open: string | null = null;
  for (const line of text.split("\n")) {
    const m = /^ {0,3}(`{3,}|~{3,})/.exec(line);
    if (!m) continue;
    const fence = m[1] as string;
    if (open === null) open = fence;
    else if (fence[0] === open[0] && fence.length >= open.length) open = null;
  }
  if (open === null) return text;
  return `${text}${text.endsWith("\n") ? "" : "\n"}${open}`;
}

/** http(s) 링크만 허용한다. */
export function isSafeHref(href: string | undefined): href is string {
  return !!href && /^https?:\/\//i.test(href.trim());
}

function textOf(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  if (isValidElement(node)) return textOf((node as ReactElement<{ children?: ReactNode }>).props.children);
  return "";
}

function CodeBlock({ children, onCopyText, messages }: { children: ReactNode; onCopyText?: (t: string) => void; messages: MarkdownMessages }) {
  const [copied, setCopied] = useState(false);
  const code = Children.toArray(children).map(textOf).join("").replace(/\n$/, "");
  const copy = () => {
    if (onCopyText) onCopyText(code);
    else void navigator.clipboard?.writeText(code);
    setCopied(true);
  };
  return (
    <div style={{ position: "relative" }}>
      <pre style={{ ...s.code, maxHeight: "none" }}>{children}</pre>
      <button type="button" className="ac-btn" data-size="sm" onClick={copy} style={{ position: "absolute", top: 4, right: 4 }}>
        {copied ? messages.copied : messages.copy}
      </button>
    </div>
  );
}

/**
 * 안전한 마크다운 표시. 원시 HTML은 렌더하지 않고(텍스트로 이스케이프), 링크는 http(s)만
 * `target=_blank rel="noopener noreferrer"`로 연다. 코드 블록에 복사 버튼.
 */
export function Markdown({ text, streaming, onCopyText, messages }: MarkdownProps) {
  const m = { ...defaultMarkdownMessages, ...messages };
  const components: Components = {
    a: ({ href, children }) =>
      isSafeHref(href) ? (
        <a href={href} target="_blank" rel="noopener noreferrer">
          {children}
        </a>
      ) : (
        <span>{children}</span>
      ),
    pre: ({ children }) => (
      <CodeBlock onCopyText={onCopyText} messages={m}>
        {children}
      </CodeBlock>
    ),
    img: ({ alt }) => <span>{alt ?? ""}</span>,
  };
  return (
    <div className="ac-text ac-markdown" style={{ overflowWrap: "anywhere", minWidth: 0 }}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components} urlTransform={(u) => (isSafeHref(u) ? u : "")}>
        {streaming ? closeOpenFence(text) : text}
      </ReactMarkdown>
    </div>
  );
}

import type { ReactNode } from "react";
import Markdown, { defaultUrlTransform, type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

export interface MarkdownPreviewProps {
  /** 마크다운 원문. */
  source: string;
  /**
   * 링크를 직접 그린다(위키 링크처럼 앱이 정한 이동 방식). 안 주면 기본 `<a>`.
   * `href`는 `urlTransform`을 거친 값이고, `children`은 링크 글자다.
   */
  renderLink?: (href: string | undefined, children: ReactNode) => ReactNode;
  /** 그리기 전에 원문을 바꾼다(서버가 준 오프셋으로 링크를 치환하는 등). 순수 함수여야 한다. */
  transformSource?: (text: string) => string;
  /** 허용 스킴을 넓히는 등 주소를 바꾼다. 기본은 react-markdown 기본값(위험한 스킴을 빈 값으로). */
  urlTransform?: (url: string) => string | null | undefined;
  className?: string;
}

/**
 * 마크다운 미리보기(react-markdown + GFM). html은 그리지 않는다. `className`이 없으면 감싸는 요소 없이 그린다(편집기 창이 이미 감싼다). 데이터·훅만 받고 API를 모른다.
 */
export function MarkdownPreview({ source, renderLink, transformSource, urlTransform, className }: MarkdownPreviewProps) {
  const text = transformSource ? transformSource(source) : source;
  const components: Components | undefined = renderLink
    ? { a: ({ href, children }) => <>{renderLink(href, children)}</> }
    : undefined;
  const body = (
    <Markdown remarkPlugins={[remarkGfm]} urlTransform={urlTransform ?? defaultUrlTransform} {...(components ? { components } : {})}>
      {text}
    </Markdown>
  );
  return className ? <div className={className}>{body}</div> : body;
}

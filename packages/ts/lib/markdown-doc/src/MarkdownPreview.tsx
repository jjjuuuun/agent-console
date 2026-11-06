import { createContext, useContext, type ReactNode } from "react";
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

type RenderLink = MarkdownPreviewProps["renderLink"];

/**
 * `renderLink`는 컨텍스트로 전한다. 컴포넌트 표를 렌더마다 새로 만들면 부모가 다시 그려질 때마다 모든 링크 요소가 지워졌다 다시 만들어져
 * 포커스·호버를 잃는다. 표를 한 번만 만들고 최신 `renderLink`를 컨텍스트로 읽으면 링크 요소가 유지된다.
 */
const RenderLinkContext = createContext<RenderLink>(undefined);
const LinkAnchor: NonNullable<Components["a"]> = ({ href, children }) => {
  const render = useContext(RenderLinkContext);
  return <>{render === undefined ? null : render(href, children)}</>;
};
const LINK_COMPONENTS: Components = { a: LinkAnchor };

/**
 * 마크다운 미리보기(react-markdown + GFM). html은 그리지 않는다. `className`이 없으면 감싸는 요소 없이 그린다(편집기 창이 이미 감싼다). 데이터·훅만 받고 API를 모른다.
 */
export function MarkdownPreview({ source, renderLink, transformSource, urlTransform, className }: MarkdownPreviewProps) {
  const text = transformSource ? transformSource(source) : source;
  const body = (
    <RenderLinkContext.Provider value={renderLink}>
      <Markdown remarkPlugins={[remarkGfm]} urlTransform={urlTransform ?? defaultUrlTransform} {...(renderLink ? { components: LINK_COMPONENTS } : {})}>
        {text}
      </Markdown>
    </RenderLinkContext.Provider>
  );
  return className ? <div className={className}>{body}</div> : body;
}

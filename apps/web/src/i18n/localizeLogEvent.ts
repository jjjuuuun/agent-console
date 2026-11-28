import type { LogEvent, LogEventPage, TextTemplate } from "@agent-console/contracts";

type Translate = (text: string) => string;
/** 틀이 딸린 칸을 옮기는 함수(`useServerRender`). 칸 값과 그 칸의 `text_templates` 항목을 받는다. */
type Render = (value: string, parts?: readonly TextTemplate[] | null) => string;

/**
 * 이벤트의 제목·한 줄 본문을 화면 언어로 옮긴다. 값이 섞인 문장("세션 시작 <id>" 등)은 서버가 준 `text_templates`
 * (`/title`·`/summary`)의 틀을 번역해 값으로 채운다(`render`가 있을 때). 틀이 없으면 고정 문구로 보고 `tr`로 옮긴다.
 * 틀 중 하나라도 번역이 없으면 서버가 쓴 원문 그대로다.
 */
export function localizeEvent(e: LogEvent, tr: Translate, render?: Render): LogEvent {
  const field = (value: string | undefined, pointer: string): string | undefined => {
    if (value === undefined) return undefined;
    const parts = e.text_templates?.[pointer];
    return render !== undefined && parts !== undefined && parts.length > 0 ? render(value, parts) : tr(value);
  };
  const title = field(e.title, "/title");
  const summary = field(e.summary, "/summary");
  if (title === e.title && summary === e.summary) return e;
  return { ...e, ...(title !== undefined ? { title } : {}), ...(summary !== undefined ? { summary } : {}) };
}

/** 이벤트 쪽 하나(목록·실행 로그)의 이벤트를 옮긴다. */
export function localizeEventPage(page: LogEventPage, tr: Translate, render?: Render): LogEventPage {
  return page.items === undefined ? page : { ...page, items: page.items.map((e) => localizeEvent(e, tr, render)) };
}


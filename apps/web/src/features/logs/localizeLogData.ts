import type { LogClassifierDescriptor, LogDashboard, LogEvent, LogEventPage, LogSourceInfo, LogTaxonomy, LogTimeline, TextTemplate } from "@agent-console/contracts";

type Translate = (text: string) => string;
/** 틀이 딸린 칸을 옮기는 함수(`useServerRender`). 칸 값과 그 칸의 `text_templates` 항목을 받는다. */
type Render = (value: string, parts?: readonly TextTemplate[] | null) => string;

const opt = (value: string | null | undefined, tr: Translate): string | null | undefined => (typeof value === "string" ? tr(value) : value);

/** 로그 출처 하나의 보이는 글자(이름·설명·설정 도움말)를 화면 언어로 옮긴다. 아이디·형식·스키마는 그대로. */
export function localizeSource(info: LogSourceInfo, tr: Translate): LogSourceInfo {
  const d = info.descriptor;
  return {
    ...info,
    descriptor: {
      ...d,
      title: tr(d.title),
      ...(d.description !== undefined ? { description: opt(d.description, tr) as string | null } : {}),
      ...(d.setup_help !== undefined ? { setup_help: opt(d.setup_help, tr) as string | null } : {}),
    },
  };
}

/** 분류 체계의 범주 이름·설명을 옮긴다(범주 아이디는 그대로). */
export function localizeTaxonomy(taxonomy: LogTaxonomy, tr: Translate): LogTaxonomy {
  if (!taxonomy.categories) return taxonomy;
  const categories = Object.fromEntries(
    Object.entries(taxonomy.categories).map(([id, c]) => [id, { ...c, ...(c.label !== undefined ? { label: opt(c.label, tr) } : {}), ...(c.description !== undefined ? { description: opt(c.description, tr) } : {}) }]),
  );
  return { ...taxonomy, categories };
}

/** 분류기 서술자의 이름·설명을 옮긴다. */
export function localizeClassifier(d: LogClassifierDescriptor, tr: Translate): LogClassifierDescriptor {
  return { ...d, title: tr(d.title), ...(d.description !== undefined ? { description: opt(d.description, tr) } : {}) };
}

/** 서버가 주는 대시보드 틀(이름·위젯 이름)을 옮긴다. 사용자가 만든 대시보드에는 쓰지 않는다. */
export function localizeDashboard(d: LogDashboard, tr: Translate): LogDashboard {
  return {
    ...d,
    title: tr(d.title),
    ...(d.widgets ? { widgets: d.widgets.map((w) => (typeof w.title === "string" ? { ...w, title: tr(w.title) } : w)) } : {}),
  };
}

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

/** 세션 타임라인의 이벤트를 옮긴다. */
export function localizeTimeline(timeline: LogTimeline, tr: Translate, render?: Render): LogTimeline {
  return timeline.events === undefined ? timeline : { ...timeline, events: timeline.events.map((e) => localizeEvent(e, tr, render)) };
}

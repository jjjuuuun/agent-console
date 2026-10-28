import type { Interaction, InteractionKindDescriptor } from "./types";

/** 판정이 쓰이는 화면. `chat` = 입력창이 있는 화면, `run-detail` = 입력창이 없는 화면(실행 상세 등). */
export type AnswerSurfaceContext = "chat" | "run-detail";

/** 답을 쓰는 칸의 주인. `composer` = 하단 입력창(해당 요청 id), `card` = 각 카드. */
export type AnswerSurface = { surface: "composer"; interactionId: string } | { surface: "card" };

export interface ResolveAnswerSurfaceInput {
  /** 이 화면에 보이는 대기 요청 전부(자식 실행 포함). */
  pending: readonly Interaction[];
  /** 종류 id → 디스크립터. */
  descriptors: ReadonlyMap<string, InteractionKindDescriptor> | Readonly<Record<string, InteractionKindDescriptor>>;
  /** 설정 `chat.answer_with_composer`. */
  answerWithComposer: boolean;
  context: AnswerSurfaceContext;
}

function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function descriptorOf(input: ResolveAnswerSurfaceInput["descriptors"], kind: string): InteractionKindDescriptor | undefined {
  if (input instanceof Map) return input.get(kind);
  const record = input as Readonly<Record<string, InteractionKindDescriptor>>;
  return Object.hasOwn(record, kind) ? record[kind] : undefined;
}

/** JSON Pointer의 첫 조각(`/response/text` → `response`). 포인터가 아니면 undefined. */
function firstSegment(pointer: string): string | undefined {
  if (!pointer.startsWith("/")) return undefined;
  const head = pointer.slice(1).split("/")[0] ?? "";
  return head === "" ? undefined : head.replace(/~1/g, "/").replace(/~0/g, "~");
}

/** 자유 텍스트 하나로 끝나는 모양인가: 질문 0~1개·선택지 없음·필수 응답 항목이 자유 텍스트 자리뿐. */
function isSingleFreeText(interaction: Interaction, descriptor: InteractionKindDescriptor, head: string): boolean {
  const questions = interaction.payload?.["questions"];
  if (questions !== undefined && questions !== null) {
    if (!Array.isArray(questions) || questions.length > 1) return false;
    const first: unknown = questions[0];
    const options = isObject(first) ? first["options"] : undefined;
    if (Array.isArray(options) && options.length > 0) return false;
  }
  const schema = interaction.response_schema ?? descriptor.response_schema;
  const required = isObject(schema) ? schema["required"] : undefined;
  if (Array.isArray(required) && required.some((r) => r !== head)) return false;
  return true;
}

/**
 * 되묻기에 답을 쓰는 칸이 입력창인지 카드인지 정한다(명세 screen-chat §10.2). 순수 함수.
 * 종류 id·렌더러 이름·문구로 분기하지 않고 디스크립터 필드와 payload·response_schema의 모양만 본다.
 * `ui_hints.answer_surface`: `"card"`면 카드, 그 밖(모르는 값 포함)은 자동 판정.
 */
export function resolveAnswerSurface(input: ResolveAnswerSurfaceInput): AnswerSurface {
  const card: AnswerSurface = { surface: "card" };
  if (input.context !== "chat" || !input.answerWithComposer || input.pending.length !== 1) return card;
  const interaction = input.pending[0]!;
  const descriptor = descriptorOf(input.descriptors, interaction.kind);
  const path = descriptor?.free_text_path;
  if (!descriptor || typeof path !== "string" || path === "") return card;
  if (descriptor.ui_hints?.["answer_surface"] === "card") return card;
  const head = firstSegment(path);
  if (head === undefined || !isSingleFreeText(interaction, descriptor, head)) return card;
  return { surface: "composer", interactionId: interaction.id };
}

/** 판정 결과 → 카드의 `answerVia`. */
export function answerViaOf(surface: AnswerSurface, interactionId: string): "inline" | "external" {
  return surface.surface === "composer" && surface.interactionId === interactionId ? "external" : "inline";
}

/** 카드가 질문 본문·힌트 줄에 다는 DOM id. 입력창 `aria-describedby`가 같은 id를 쓴다. */
export function answerCardIds(interactionId: string): { body: string; hint: string } {
  return { body: `ac-answer-body-${interactionId}`, hint: `ac-answer-hint-${interactionId}` };
}

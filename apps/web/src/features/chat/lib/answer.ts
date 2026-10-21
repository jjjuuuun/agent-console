import type { Interaction, InteractionKindDescriptor } from "@agent-console/contracts";
import { setAt } from "../../../lib/jsonPointer";

export interface AnswerTarget {
  interaction: Interaction;
  descriptor: InteractionKindDescriptor;
}

/** payload의 질문 수. 질문 배열이 없으면 1로 본다. */
export function questionCount(interaction: Interaction): number {
  const q = interaction.payload?.["questions"];
  return Array.isArray(q) ? q.length : 1;
}

/**
 * 입력창 답변 모드 판정(종류 이름은 쓰지 않는다): 대기 상호작용이 정확히 하나, 그 종류에 `free_text_path`가 있고,
 * 설정이 켜져 있고, 질문이 둘 이상이 아니다.
 */
export function answerTarget(pending: readonly Interaction[], descriptors: ReadonlyMap<string, InteractionKindDescriptor>, enabled: boolean): AnswerTarget | null {
  if (!enabled || pending.length !== 1) return null;
  const interaction = pending[0]!;
  const descriptor = descriptors.get(interaction.kind);
  if (!descriptor?.free_text_path || questionCount(interaction) >= 2) return null;
  return { interaction, descriptor };
}

/** 입력창 텍스트를 종류의 `free_text_path`(JSON Pointer) 자리에 넣은 응답. */
export function buildResponse(descriptor: Pick<InteractionKindDescriptor, "free_text_path">, text: string): Record<string, unknown> {
  const path = descriptor.free_text_path;
  if (!path) throw new Error("free_text_path가 없는 종류에는 입력창으로 답할 수 없습니다");
  return setAt({}, path, text) as Record<string, unknown>;
}

/** 대기 목록에서 [답을 새 메시지로 보내기]에 쓸 인용 초안. 마지막 두 줄은 비워 커서를 둘 자리를 만든다. */
export function quoteForResend(interaction: Interaction, requesterLabel: string, template: (args: { who: string; question: string }) => string, optionsLine: (options: string[]) => string): string {
  const questions = Array.isArray(interaction.payload?.["questions"]) ? (interaction.payload!["questions"] as Record<string, unknown>[]) : [];
  const first = questions[0];
  const question = (typeof first?.question === "string" ? first.question : undefined) ?? interaction.title ?? interaction.message ?? "";
  const options = Array.isArray(first?.options) ? (first.options as Record<string, unknown>[]).map((o) => o.label).filter((l): l is string => typeof l === "string") : [];
  const head = template({ who: requesterLabel, question: question.split("\n")[0] ?? "" });
  return `${head}\n${options.length > 0 ? `${optionsLine(options)}\n` : ""}\n`;
}

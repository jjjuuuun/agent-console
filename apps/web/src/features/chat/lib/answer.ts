import type { Interaction, InteractionKindDescriptor } from "@agent-console/contracts";
import { setAt } from "../../../lib/jsonPointer";

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

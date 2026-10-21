import type { ResourceAttachment } from "@agent-console/contracts";

/** 서버가 예전에 저장된 평문 비밀을 가려서 돌려주는 값. 이 값을 그대로 저장하면 서버가 거부한다. */
export const MASKED_SECRET = "***";

/** 첨부 목록 위치(JSON Pointer, 예: `/resources`) 아래의 서버 오류를 첨부 번호별 메시지로 모은다. */
export function attachmentErrorsAt(errors: readonly { path: string; message: string }[] | undefined, listPointer: string): Record<number, string[]> {
  const out: Record<number, string[]> = {};
  const prefix = `${listPointer}/`;
  for (const e of errors ?? []) {
    if (!e.path.startsWith(prefix)) continue;
    const index = Number(e.path.slice(prefix.length).split("/", 1)[0]);
    if (Number.isInteger(index)) (out[index] ??= []).push(e.message);
  }
  return out;
}

/** 첨부의 설정 덮어쓰기에 가려진 비밀(`***`)이 들어 있는가. */
export function hasMaskedSecret(attachment: ResourceAttachment): boolean {
  const override = (attachment as { config_override?: unknown }).config_override;
  return override !== undefined && override !== null && JSON.stringify(override).includes(`"${MASKED_SECRET}"`);
}

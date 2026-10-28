/**
 * 비밀 거부 안내 띠. 어디에 있는지(`field`)만 말하고 찾은 값·규칙 id는 어디에도 보이지 않는다.
 * "그래도 저장"·"가리고 저장" 버튼은 없다(가림은 설정에서 정한다).
 */
import { Banner, Button } from "@agent-console/ui";
import { memoryMessages as t } from "./messages";

export interface SecretBandProps {
  /** 계약 `MemorySecretRejectedDetails.field`. 모르면 null(일반 문구) */
  field: "content" | "key" | "tags" | null;
  /** 해당 입력으로 포커스를 옮긴다 */
  onGo: () => void;
}

export function SecretBand({ field, onGo }: SecretBandProps) {
  const where = field === null ? undefined : t.band.secretWhere[field];
  const go = field === null ? t.band.secretGoDefault : (t.band.secretGo[field] ?? t.band.secretGoDefault);
  return (
    <Banner tone="danger" title={t.band.secretTitle} className="mem-band" actions={<Button size="sm" onClick={onGo}>{go}</Button>}>
      {where === undefined ? t.band.secretBody : t.band.secretBodyAt(where)}
    </Banner>
  );
}

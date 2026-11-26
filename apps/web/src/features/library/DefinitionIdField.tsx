import { useId, useState } from "react";
import { idProblem, suggestId } from "./ids";
import { libraryMessages as t } from "./messages";

export interface DefinitionId {
  /** 화면에 보일 id: 직접 고친 값, 없으면 이름에서 제안한 값 */
  id: string;
  /** 직접 고치기(고치면 제안이 멈춘다) */
  setId: (next: string) => void;
  /** 검사 결과(빈 값이면 문제 없음으로 본다. 제출 가능 여부는 `invalid`) */
  problem: "empty" | "pattern" | "duplicate" | "reserved" | undefined;
  /** 제출을 막아야 하는가(id가 비었거나 규칙 위반) */
  invalid: boolean;
}

/** 이름에서 id를 자동 제안하고(직접 고치면 멈춘다) 중복·규칙·예약어(`reserved`, 서버가 준 목록)를 즉시 검사한다. 새 정의 만들기 대화상자와 서랍이 같이 쓴다. */
export function useDefinitionId(name: string, existingIds: ReadonlySet<string>, fallbackId: string, reserved: Iterable<string> = []): DefinitionId {
  const [edited, setEdited] = useState<string | null>(null);
  const id = edited ?? (name.trim() === "" ? "" : suggestId(name, existingIds, fallbackId));
  const raw = idProblem(id, existingIds, reserved);
  return { id, setId: setEdited, problem: id === "" ? undefined : raw, invalid: raw !== undefined };
}

export interface DefinitionIdFieldProps {
  id: string;
  problem: DefinitionId["problem"];
  onChange: (next: string) => void;
  /** 입력 요소 id(라벨 연결·포커스). 생략하면 자동 */
  inputId?: string;
  /** 도움말·오류 요소 id. 제출 버튼이 `aria-describedby`로 이유를 가리킬 때 넘긴다(생략하면 자동) */
  noteId?: string;
}

/** id 입력 한 줄: 라벨, 입력, 도움말 또는 오류(`role=alert`). */
export function DefinitionIdField({ id, problem, onChange, inputId, noteId }: DefinitionIdFieldProps) {
  const uid = useId();
  const input = inputId ?? `${uid}-id`;
  const note = noteId ?? `${uid}-id-note`;
  return (
    <div className="lib-field">
      <label htmlFor={input}>{t.newDialog.id}</label>
      <input id={input} className="ac-input ac-mono" value={id} onChange={(e) => onChange(e.target.value)} aria-invalid={problem !== undefined} aria-describedby={note} />
      <span id={note} className={problem ? "lib-field-error" : "app-muted lib-field-note"} role={problem ? "alert" : undefined}>
        {problem ? t.newDialog.idErrors[problem] : t.newDialog.idHint}
      </span>
    </div>
  );
}

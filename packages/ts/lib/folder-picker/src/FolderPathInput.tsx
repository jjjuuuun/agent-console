import { useRef, type KeyboardEvent, type ReactElement, type ReactNode, type Ref } from "react";

import type { FolderCheckState } from "./checkState";
import { FolderCheckResult, type FolderCheckResultProps } from "./FolderCheckResult";
import type { Translate } from "./messages";

export interface FolderPathInputProps extends Pick<FolderCheckResultProps, "onCreate" | "creating" | "onRecheck" | "onOpenProject" | "checkingDelayMs" | "configDir"> {
  /** 컴포넌트 안 id 접두. 같은 화면에 둘 이상이면 서로 다르게. */
  id: string;
  value: string;
  /** 입력이 바뀜. `paste`면 붙여넣기로 바뀐 것(바로 확인해야 한다). */
  onValueChange: (value: string, source: "type" | "paste") => void;
  /** blur. */
  onBlur?: () => void;
  /** Enter(IME 조합 중에는 호출하지 않는다). */
  onEnter?: () => void;
  state: FolderCheckState;
  t: Translate;
  disabled?: boolean;
  inputRef?: Ref<HTMLInputElement>;
  /** 입력 오른쪽 자리(찾아보기 버튼 등). */
  trailing?: ReactNode;
  /** 입력 줄 위의 라벨을 가린다(앱이 따로 라벨을 그릴 때). */
  hideLabel?: boolean;
  /** 입력 라벨 문구(기본 `folder.path.label`). */
  label?: string;
  /** false면 확인 결과 영역을 그리지 않는다(부모가 `${id}-result` 요소를 따로 그릴 때). 기본 true. */
  showResult?: boolean;
}

/** 경로 입력 + 도움말 + 확인 결과. 표현 컴포넌트라 확인 로직은 `useFolderCheck`가 맡는다. */
export function FolderPathInput(props: FolderPathInputProps): ReactElement {
  const { id, value, onValueChange, onBlur, onEnter, state, t, disabled, inputRef, trailing, hideLabel, label, showResult = true, ...resultProps } = props;
  const pasted = useRef(false);
  const helpId = `${id}-help`;
  const resultId = `${id}-result`;
  const invalid = state.tone === "danger" && state.group !== "checking";

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.nativeEvent.isComposing && e.keyCode !== 229) {
      e.preventDefault();
      onEnter?.();
    }
  };
  // 붙여넣기 직후 값은 change 이벤트가 알려준다. 그때 즉시 확인하도록 표시만 남긴다.
  const onPaste = () => {
    pasted.current = true;
  };
  return (
    <div className="ac-fp-root ac-fp-pathinput">
      <label className={hideLabel ? "ac-fp-sr" : "ac-fp-label"} htmlFor={`${id}-input`}>{label ?? t("folder.path.label")}</label>
      <div className="ac-fp-inputrow">
        <input
          id={`${id}-input`}
          ref={inputRef}
          className="ac-fp-input"
          type="text"
          value={value}
          disabled={disabled}
          placeholder={t("folder.path.placeholder")}
          spellCheck={false}
          autoComplete="off"
          autoCapitalize="off"
          aria-describedby={`${helpId} ${resultId}`}
          aria-invalid={invalid ? "true" : undefined}
          onChange={(e) => {
            const source = pasted.current ? "paste" : "type";
            pasted.current = false;
            onValueChange(e.target.value, source);
          }}
          onPaste={onPaste}
          onBlur={onBlur}
          onKeyDown={onKeyDown}
        />
        {trailing}
      </div>
      <p id={helpId} className="ac-fp-help">{t("folder.path.help")}</p>
      {showResult ? <FolderCheckResult id={resultId} state={state} t={t} {...resultProps} /> : null}
    </div>
  );
}

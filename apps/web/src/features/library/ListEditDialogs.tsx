import { folderOf } from "@agent-console/list-arrange";
import { FolderMoveDialog } from "./FolderMoveDialog";
import { LabelEditDialog } from "./LabelEditDialog";
import { folderPathsOf, type ArrangeableDefinition } from "./arrangeDefs";
import type { ArrangeMessages } from "./arrangeMessages";
import type { DefinitionEdits } from "./useDefinitionEdits";

export interface ListEditDialogsProps<T extends ArrangeableDefinition & { id: string }> {
  /** 폴더 이동 대상(없으면 닫힘) */
  moving: T | undefined;
  /** 라벨 편집 대상(없으면 닫힘) */
  labeling: T | undefined;
  onCloseMove: () => void;
  onCloseLabels: () => void;
  /** 이동 후보를 만들 전체 목록 */
  items: readonly T[];
  edits: DefinitionEdits;
  messages: Pick<ArrangeMessages, "move" | "labels">;
}

/** 폴더 이동·라벨 편집 대화상자 한 쌍(M·L 단축키 대상). 저장은 `edits`가 한다. 에이전트·팀·리소스 목록이 함께 쓴다. */
export function ListEditDialogs<T extends ArrangeableDefinition & { id: string }>({ moving, labeling, onCloseMove, onCloseLabels, items, edits, messages: m }: ListEditDialogsProps<T>) {
  return (
    <>
      {moving === undefined ? null : (
        <FolderMoveDialog
          open
          itemName={moving.name}
          current={folderOf(moving.attributes)}
          folders={folderPathsOf(items)}
          messages={m.move}
          onClose={onCloseMove}
          onPick={(folder) => {
            onCloseMove();
            void edits.moveToFolder(moving.id, moving.name, folder);
          }}
        />
      )}
      {labeling === undefined ? null : (
        <LabelEditDialog
          open
          itemName={labeling.name}
          labels={labeling.labels ?? []}
          messages={m.labels}
          onClose={onCloseLabels}
          onSave={(labels) => {
            onCloseLabels();
            void edits.saveLabels(labeling.id, labeling.name, labels);
          }}
        />
      )}
    </>
  );
}

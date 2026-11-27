import { useState } from "react";
import { Icon, Menu, Popover, type MenuItemDef } from "@agent-console/ui";
import { useT } from "@agent-console/i18n";

export interface MemoryStoreChipProps {
  /** 지금 보는 저장소가 공용인가 */
  library: boolean;
  /** 고를 수 있는 프로젝트 저장소(없으면 칩은 글자만, 메뉴 없음) */
  project: { name: string } | null;
  /** 저장소를 고른다(true = 공용) */
  onSelect: (library: boolean) => void;
}

/**
 * 메모리 머리의 저장소 칩(screen-memory §1.3): `이 프로젝트: {이름}`(기본, 경로는 `ProjectChip`이 보인다) / `공용` 메뉴. 프로젝트가 없으면 `공용`만 보이는 글자 칩.
 * 모양은 구성 화면의 공간 칩(`space-chip`)과 같다. 데이터와 콜백은 props로만 받는다.
 */
export function MemoryStoreChip({ library, project, onSelect }: MemoryStoreChipProps) {
  const t = useT("memory");
  const [open, setOpen] = useState(false);
  const label = library || project === null ? t("store.library") : t("store.project", { name: project.name });
  const shown = library || project === null;
  const body = (
    <>
      <Icon name={shown ? "library" : "folder"} size={14} />
      <span className="ac-ellipsis space-chip-name">{label}</span>
    </>
  );
  if (project === null) {
    return <span className="space-chip mem-store-chip" data-memory-store="library" aria-label={`${t("store.label")}: ${label}`}>{body}</span>;
  }
  const items: MenuItemDef[] = [
    { id: "current", label: t("store.project", { name: project.name }), icon: library ? undefined : "check", onSelect: () => onSelect(false) },
    { id: "library", label: t("store.library"), icon: library ? "check" : undefined, onSelect: () => onSelect(true) },
  ];
  return (
    <Popover
      open={open}
      onOpenChange={setOpen}
      panelRole="menu"
      panelLabel={t("store.menuLabel")}
      align="end"
      renderTrigger={(p) => (
        <button {...p} type="button" className="space-chip mem-store-chip" data-memory-store={shown ? "library" : "current"} aria-label={`${t("store.label")}: ${label}`}>
          {body}
          <Icon name="chevron-down" size={12} />
        </button>
      )}
    >
      <Menu items={items} onClose={() => setOpen(false)} />
    </Popover>
  );
}

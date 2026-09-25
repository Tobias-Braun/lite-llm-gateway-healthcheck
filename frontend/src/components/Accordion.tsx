import { useState } from "react";
import type { ModelFamily } from "../types";
import { FamilyPanel } from "./FamilyPanel";

interface AccordionProps {
  families: ModelFamily[];
}

/** Lists one panel per family; panels open independently, keyed by title so state survives refreshes. */
export function Accordion({ families }: AccordionProps) {
  const [openTitles, setOpenTitles] = useState<Set<string>>(() => new Set());

  function toggle(title: string) {
    setOpenTitles((previous) => {
      const next = new Set(previous);
      if (next.has(title)) {
        next.delete(title);
      } else {
        next.add(title);
      }
      return next;
    });
  }

  return (
    <div className="accordion">
      {families.map((family) => (
        <FamilyPanel
          key={family.title}
          family={family}
          open={openTitles.has(family.title)}
          onToggle={() => toggle(family.title)}
        />
      ))}
    </div>
  );
}

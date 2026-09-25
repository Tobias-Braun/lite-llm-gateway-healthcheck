import { useId } from "react";
import type { ModelFamily } from "../types";
import { AvailabilityTimeline } from "./AvailabilityTimeline";
import { ModelTable } from "./ModelTable";
import { StatusDot } from "./StatusDot";

interface FamilyPanelProps {
  family: ModelFamily;
  open: boolean;
  onToggle: () => void;
}

/** Accordion panel: head and timeline are always visible, the model table collapses. */
export function FamilyPanel({ family, open, onToggle }: FamilyPanelProps) {
  const contentId = useId();

  return (
    <section className={`panel${open ? " panel-open" : ""}`}>
      <h2 className="panel-heading">
        <button type="button" className="panel-head" aria-expanded={open} aria-controls={contentId} onClick={onToggle}>
          <span className="chevron" aria-hidden="true" />
          <StatusDot status={family.status} />
          <span className="panel-title">{family.title}</span>
          <span className="panel-count muted">
            {family.models.length} {family.models.length === 1 ? "model" : "models"}
          </span>
        </button>
      </h2>
      <AvailabilityTimeline points={family.history.availabilityPoints} />
      <div id={contentId} className="panel-content" hidden={!open}>
        <ModelTable models={family.models} />
      </div>
    </section>
  );
}

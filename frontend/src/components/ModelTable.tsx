import { Fragment, useState } from "react";
import type { ModelDef } from "../types";
import { AVAILABILITY_LABEL, formatDateTime, formatLatency, formatUptime } from "../format";
import { AvailabilityTimeline } from "./AvailabilityTimeline";
import { ModelDetail } from "./ModelDetail";
import { StatusDot } from "./StatusDot";

interface ModelTableProps {
  family: string;
  models: ModelDef[];
}

const COLUMNS = 6;

/** Builds the per-model tooltip: the error for failed checks, otherwise status, latency and check time. */
function modelTooltip(model: ModelDef): string {
  if (model.error) {
    return model.error;
  }
  const parts = [AVAILABILITY_LABEL[model.status]];
  if (model.latencyMs !== null) {
    parts.push(`${model.latencyMs} ms`);
  }
  if (model.lastChecked) {
    parts.push(`checked ${formatDateTime(model.lastChecked)}`);
  }
  return parts.join(", ");
}

export function ModelTable({ family, models }: ModelTableProps) {
  // Keyed by model name, so an expanded row stays open across the periodic refresh.
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());

  function toggle(name: string) {
    setExpanded((previous) => {
      const next = new Set(previous);
      if (!next.delete(name)) {
        next.add(name);
      }
      return next;
    });
  }

  if (models.length === 0) {
    return <p className="muted">No models configured.</p>;
  }

  return (
    <table className="model-table">
      <thead>
        <tr>
          <th>Name</th>
          <th>Provider</th>
          <th>Company</th>
          <th>Latency</th>
          <th>Uptime</th>
          <th title="Shows the model's own most recent rounds — a shorter, more recent window than the family timeline above">
            History
          </th>
        </tr>
      </thead>
      <tbody>
        {models.map((model) => {
          const open = expanded.has(model.modelname);
          return (
            <Fragment key={model.modelname}>
              <tr className={open ? "model-row-open" : undefined}>
                <td>
                  <StatusDot status={model.status} title={modelTooltip(model)} />
                  <button
                    type="button"
                    className="model-toggle"
                    aria-expanded={open}
                    onClick={() => toggle(model.modelname)}
                  >
                    <span className="model-name">{model.modelname}</span>
                  </button>
                </td>
                <td>{model.provider}</td>
                <td>{model.company}</td>
                <td>{formatLatency(model)}</td>
                <td>{formatUptime(model.history.availabilityPoints)}</td>
                <td>
                  <AvailabilityTimeline points={model.history.availabilityPoints} small />
                </td>
              </tr>
              {open && (
                <tr className="model-detail-row">
                  <td colSpan={COLUMNS}>
                    <ModelDetail family={family} model={model.modelname} />
                  </td>
                </tr>
              )}
            </Fragment>
          );
        })}
      </tbody>
    </table>
  );
}

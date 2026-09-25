import type { ModelDef } from "../types";
import { AVAILABILITY_LABEL, formatDateTime } from "../format";
import { StatusDot } from "./StatusDot";

interface ModelTableProps {
  models: ModelDef[];
}

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

export function ModelTable({ models }: ModelTableProps) {
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
        </tr>
      </thead>
      <tbody>
        {models.map((model) => (
          <tr key={model.modelname}>
            <td>
              <StatusDot status={model.status} title={modelTooltip(model)} />
              <span className="model-name">{model.modelname}</span>
            </td>
            <td>{model.provider}</td>
            <td>{model.company}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

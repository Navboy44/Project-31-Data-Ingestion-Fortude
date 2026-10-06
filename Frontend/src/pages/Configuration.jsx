import React, { useState } from "react";
import Card from "../components/Card";
import Row from "../components/Row";
import PageHeading from "../components/PageHeading";
import Pipelines from "../components/Pipelines";

// Maps the flat UI key to a human-readable label used in the add-modal.
const SECTIONS = [
  ["connectors", "Connectors", "Connector"],
  ["rules", "Rules", "Rule"],
  ["outputs", "Output Targets", "Output Target"],
];

/**
 * Small inline modal that captures the name of a new config item.
 */
function AddModal({ prefix, onConfirm, onCancel }) {
  const [name, setName] = useState("");

  const submit = (e) => {
    e.preventDefault();
    const trimmed = name.trim();
    if (trimmed) onConfirm(trimmed);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
      <div className="w-full max-w-sm rounded-3xl border border-[color:var(--border)] bg-[color:var(--card)] p-6 shadow-2xl">
        <h3 className="text-lg font-semibold text-[color:var(--text)] mb-4">
          Add {prefix}
        </h3>
        <form onSubmit={submit} className="space-y-4">
          <input
            autoFocus
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={`${prefix} name...`}
            className="w-full rounded-2xl border border-[color:var(--borderSoft)] bg-[color:var(--bg)] px-4 py-3 text-sm text-[color:var(--text)] outline-none focus:border-[color:var(--blue)] focus:ring-2 focus:ring-[color:var(--blueSoft)]"
          />
          <div className="flex gap-3 justify-end">
            <button
              type="button"
              onClick={onCancel}
              className="config-button config-button-secondary"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!name.trim()}
              className="config-button config-button-create"
            >
              Add
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

/**
 * Configure page - lists all connectors, rules, and output targets stored in
 * the backend and lets the user add or remove them.
 */
export default function Configure({
  config,
  configLoading,
  addRow,
  removeConfigRow,
  pipelines = [],
  pipelinesLoading = false,
  pipelinesError = "",
  onRetryPipelines,
  onCreatePipeline,
  onUpdatePipeline,
  onDeletePipeline,
}) {
  // Which section's add-modal is open, or null if none.
  const [adding, setAdding] = useState(null); // "connectors" | "rules" | "outputs" | null

  const handleConfirm = async (key, name) => {
    setAdding(null);
    await addRow(key, name);
  };

  return (
    <section>
      <PageHeading
        title="Configuration"
        subtitle="Manage connectors, rules, and output targets."
      />

      {configLoading ? (
        <div className="text-sm text-[color:var(--textMuted)] py-8 text-center">
          Loading configuration...
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {SECTIONS.map(([key, title, prefix]) => (
            <Card
              roundedActions
              key={key}
              title={title}
              count={config[key].length}
              footer={`+ Add ${prefix}`}
              onFooterClick={() => setAdding(key)}
            >
              <div style={{ maxHeight: 420, overflowY: "auto" }}>
                {config[key].map((item) => (
                  <Row
                    roundedActions
                    key={item.id}
                    label={item.name}
                    onEdit={() => {}}
                    onDelete={() => removeConfigRow(key, item.id, item.name)}
                  />
                ))}
              </div>
            </Card>
          ))}
        </div>
      )}

      {adding && (
        <AddModal
          prefix={SECTIONS.find(([k]) => k === adding)?.[2]}
          onConfirm={(name) => handleConfirm(adding, name)}
          onCancel={() => setAdding(null)}
        />
      )}
      {!configLoading && (
        <div className="mt-6">
          <Pipelines
            config={config}
            pipelines={pipelines}
            loading={pipelinesLoading}
            loadError={pipelinesError}
            onRetry={onRetryPipelines}
            onCreate={onCreatePipeline}
            onUpdate={onUpdatePipeline}
            onDelete={onDeletePipeline}
          />
        </div>
      )}
    </section>
  );
}

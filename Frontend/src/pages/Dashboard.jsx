import React from "react";
import { COLORS } from "../theme";
import Card from "../components/Card";
import Row from "../components/Row";
import PageHeading from "../components/PageHeading";

// Dashboard page shows a high-level summary of recent ingestions and configuration items.
export default function Dashboard({ history, config, goTo, openEntry }) {
  // Shows the most recent five ingestion entries in reverse chronological order.
  const dashboardEntries = history.slice(-5).reverse();

  // Total number of configuration items across all categories (connectors + rules + outputs).
  const totalConfig =
    config.connectors.length + config.rules.length + config.outputs.length;

  // Interleave the three config categories into a flat preview list for the card,
  // showing a maximum of 5 items so the card stays compact.
  const configPreview = [
    ...config.connectors.map((c) => ({ name: c.name, sub: "Connector" })),
    ...config.rules.map((r) => ({ name: r.name, sub: "Rule" })),
    ...config.outputs.map((o) => ({ name: o.name, sub: "Output" })),
  ].slice(0, 5);

  return (
    <section>
      <PageHeading
        title="Dashboard"
        subtitle="An overview of your ingestion pipelines and configuration."
      />

      <div className="mb-5">
        <button
          onClick={() => goTo("ingest")}
          className="font-semibold text-sm px-5 py-2.5 rounded-md border-none cursor-pointer text-white"
          style={{ background: COLORS.orange }}
        >
          Start Ingestion
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-start">
        <Card
          title="Past Ingestions"
          count={history.length}
          footer="View all &rarr;"
          onFooterClick={() => goTo("history")}
        >
          {dashboardEntries.map((e) => (
            <Row
              key={e.id}
              label={`Entry ${e.id}`}
              sub={e.connector}
              onEdit={() => openEntry(e.id)}
            />
          ))}
        </Card>

        <Card
          title="Configurations"
          count={totalConfig}
          footer="View all &rarr;"
          onFooterClick={() => goTo("configure")}
        >
          {configPreview.length === 0 ? (
            <div className="text-sm text-[color:var(--textMuted)] py-2">
              No configuration items yet.
            </div>
          ) : (
            configPreview.map(({ name, sub }) => (
              <Row
                key={`${sub}-${name}`}
                label={name}
                sub={sub}
                onEdit={() => goTo("configure")}
              />
            ))
          )}
        </Card>
      </div>
    </section>
  );
}

import React, { useState } from "react";
import { COLORS } from "../theme";
import { MAPPER_OPTIONS } from "../data";
import Select from "../components/Select";
import PageHeading from "../components/PageHeading";

// Animated spinner SVG
function Spinner() {
  return (
    <svg
      width="48"
      height="48"
      viewBox="0 0 48 48"
      fill="none"
      style={{ animation: "spin 0.9s linear infinite" }}
    >
      <circle cx="24" cy="24" r="20" stroke={COLORS.border} strokeWidth="4" />
      <path
        d="M44 24a20 20 0 0 0-20-20"
        stroke={COLORS.orange}
        strokeWidth="4"
        strokeLinecap="round"
      />
    </svg>
  );
}

/**
 * NewIngestion page.
 *
 * Props:
 *   form      { connector, mapper, rules, outputs }
 *   setForm   setter
 *   config    { connectors: [{id,name}], rules: [{id,name}], outputs: [{id,name}] }
 *   onStart   async () => void
 */
export default function NewIngestion({ form, setForm, config, onStart }) {
  const [status, setStatus] = useState("form"); // "form" | "loading" | "error"
  const [errorMessage, setErrorMessage] = useState("");
  const { connector, mapper, rules, outputs } = form;
  const isInfor = connector.toLowerCase().includes("infor");
  const validOrder = form.order_type && /^[A-Za-z0-9_-]{1,50}$/.test((form.order_number || "").trim());
  const allFilled = connector && mapper && rules && outputs && (!isInfor || validOrder);

  // Build option arrays from live config data (just the name strings for the <select>).
  const connectorOptions = config.connectors.map((c) => c.name);
  const rulesOptions = config.rules.map((r) => r.name);
  const outputOptions = config.outputs.map((o) => o.name);

  const fields = [
    ["Select Connector", "connector", connector, connectorOptions],
    ["Select Mapper",    "mapper",    mapper,    MAPPER_OPTIONS],
    ["Select Rules",     "rules",     rules,     rulesOptions],
    ["Select Outputs",   "outputs",   outputs,   outputOptions],
  ];

  const handleStart = async () => {
    setStatus("loading");
    setErrorMessage("");
    try {
      await onStart({ onError: (msg) => { setErrorMessage(msg); setStatus("error"); } });
      // If onStart succeeds it navigates to dashboard — if we reach here something unexpected happened
    } catch (err) {
      setErrorMessage(err.message || "Something went wrong. Please try again.");
      setStatus("error");
    }
  };

  // ── Loading screen ────────────────────────────────────────────────────────
  if (status === "loading") {
    return (
      <div
        className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-6"
        style={{ background: "rgba(0,0,0,0.45)", backdropFilter: "blur(4px)" }}
      >
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        <div
          className="flex flex-col items-center gap-6 rounded-2xl p-10 shadow-2xl"
          style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, minWidth: 320 }}
        >
          <Spinner />
          <div className="text-center">
            <div className="font-semibold text-base mb-1" style={{ color: COLORS.text }}>
              Running ingestion…
            </div>
            <div className="text-sm" style={{ color: COLORS.textMuted }}>
              Fetching data from <span className="font-medium" style={{ color: COLORS.orange }}>{connector}</span>
            </div>
          </div>
          <div className="flex gap-1.5 mt-1">
            {[0, 150, 300].map((delay) => (
              <span
                key={delay}
                style={{
                  width: 8, height: 8, borderRadius: "50%",
                  background: COLORS.orange,
                  animation: `pulse 1.2s ease-in-out ${delay}ms infinite`,
                  display: "inline-block",
                }}
              />
            ))}
          </div>
          <style>{`@keyframes pulse { 0%,100%{opacity:.2;transform:scale(0.8)} 50%{opacity:1;transform:scale(1.2)} }`}</style>
        </div>
      </div>
    );
  }

  // ── Error screen ──────────────────────────────────────────────────────────
  if (status === "error") {
    return (
      <section>
        <PageHeading title="Ingestion Failed" subtitle="Something went wrong while processing your request." />
        <div
          className="rounded-xl p-10 flex flex-col items-center gap-6 text-center"
          style={{ background: COLORS.card, border: `1px solid ${COLORS.red}` }}
        >
          {/* Error icon */}
          <div
            className="flex items-center justify-center rounded-full"
            style={{ width: 64, height: 64, background: "#fee2e2" }}
          >
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="10" fill="#dc2626" />
              <path d="M12 7v5" stroke="white" strokeWidth="2" strokeLinecap="round" />
              <circle cx="12" cy="16.5" r="1" fill="white" />
            </svg>
          </div>

          <div>
            <div className="font-semibold text-lg mb-2" style={{ color: COLORS.text }}>
              Ingestion could not complete
            </div>
            <div
              className="text-sm rounded-lg px-4 py-3 max-w-lg mx-auto break-words"
              style={{ background: "#fee2e2", color: "#991b1b", border: "1px solid #fca5a5" }}
            >
              {errorMessage}
            </div>
          </div>

          <div className="flex gap-3 flex-wrap justify-center">
            <button
              onClick={() => setStatus("form")}
              className="font-semibold text-sm px-6 py-2.5 rounded-md border-none cursor-pointer text-white"
              style={{ background: COLORS.orange }}
            >
              ← Go back &amp; retry
            </button>
          </div>
        </div>
      </section>
    );
  }

  // ── Form ──────────────────────────────────────────────────────────────────
  return (
    <section>
      <PageHeading title="New Data Ingestion" subtitle="Wire a connector to a mapper, apply rules, and send the result to an output target." />

      {/* Pipeline indicator */}
      <div className="relative flex items-center justify-between rounded-lg px-8 py-6 mb-6" style={{ background: COLORS.card, border: `1px solid ${COLORS.border}` }}>
        <div className="absolute h-0.5" style={{ top: 33, left: 60, right: 60, background: COLORS.border, zIndex: 1 }} />
        {fields.map(([label, key, val]) => (
          <div key={key} className="flex flex-col items-center gap-2.5 flex-1 relative" style={{ zIndex: 2 }}>
            <div
              className="rounded-full transition-all"
              style={{
                width: 14,
                height: 14,
                background: val ? COLORS.orange : "#ffffff",
                border: `2px solid ${val ? COLORS.orange : COLORS.border}`,
              }}
            />
            <div className="text-xs font-medium" style={{ color: val ? COLORS.orange : COLORS.textFaint }}>
              {label.replace("Select ", "")}
            </div>
          </div>
        ))}
      </div>

      <div className="rounded-lg p-8" style={{ background: COLORS.card, border: `1px solid ${COLORS.border}` }}>
        <div className="grid gap-6" style={{ gridTemplateColumns: "180px 1fr" }}>
          {fields.map(([label, key, val, opts]) => (
            <React.Fragment key={key}>
              <label htmlFor={key} className="font-semibold text-sm self-center cursor-pointer" style={{ color: COLORS.text }}>{label}</label>
              <Select id={key} value={val} onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value,
                ...(key === "connector" ? {
                  outputs: e.target.value.toLowerCase().includes("infor") ? "Local JSON" : "",
                } : {}),
              }))} options={key === "outputs" && isInfor ? ["Local JSON"] : opts} placeholder="Select from the following options" />
            </React.Fragment>
          ))}
        </div>
        {isInfor && (
          <div className="grid gap-4 mt-6">
            <label htmlFor="order_type" className="font-semibold text-sm">Order type</label>
            <select id="order_type" value={form.order_type || ""}
              onChange={(e) => setForm((f) => ({ ...f, order_type: e.target.value }))}
              className="w-full px-3.5 py-2.5 rounded-md"
              style={{ background: COLORS.card, color: COLORS.text, border: `1px solid ${COLORS.border}` }}>
              <option value="">Select an order type</option>
              <option value="customer">Customer order</option>
              <option value="purchase">Purchase order</option>
            </select>
            <label htmlFor="order_number" className="font-semibold text-sm">Order number</label>
            <input id="order_number" value={form.order_number || ""} maxLength={50}
              onChange={(e) => setForm((f) => ({ ...f, order_number: e.target.value }))}
              placeholder={form.order_type === "purchase" ? "Purchase order number (PUNO)" : "Customer order number (ORNO)"}
              className="w-full px-3.5 py-2.5 rounded-md"
              style={{ background: COLORS.card, color: COLORS.text, border: `1px solid ${COLORS.border}` }} />
            <p className="text-sm" style={{ color: COLORS.textMuted }}>
              Enter 1–50 letters, digits, underscores or hyphens. Order lines are saved as local JSON.
            </p>
          </div>
        )}
        <div className="flex justify-end mt-8">
          <button
            disabled={!allFilled}
            onClick={handleStart}
            className="font-semibold text-sm px-6 py-2.5 rounded-md border-none text-white"
            style={{
              background: allFilled ? COLORS.orange : COLORS.badgeBg,
              color: allFilled ? "#ffffff" : COLORS.textFaint,
              cursor: allFilled ? "pointer" : "not-allowed",
            }}
          >
            Start
          </button>
        </div>
      </div>
    </section>
  );
}

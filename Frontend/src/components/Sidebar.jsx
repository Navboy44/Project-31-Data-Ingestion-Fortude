import React from "react";
import { LayoutGrid, Activity, History as HistoryIcon, Settings } from "lucide-react";
import { COLORS } from "../theme";

// The list of page links shown in the left navigation area.
const NAV_ITEMS = [
  { key: "dashboard", label: "Dashboard", icon: LayoutGrid },
  { key: "ingest", label: "Ingest", icon: Activity },
  { key: "history", label: "History", icon: HistoryIcon },
  { key: "configure", label: "Configuration", icon: Settings },
];

// Sidebar renders the main navigation and the user profile section on the left side of the app.
export default function Sidebar({ page, goTo, user = null, onSignOut = () => {} }) {
  const initials = (() => {
    if (!user) return "AS";
    const parts = String(user).split(/\s+/).filter(Boolean);
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[1][0]).toUpperCase();
  })();

  const displayName = user || "Amanda Smith";

  return (
    <div
      className="flex h-full overflow-y-auto flex-col justify-between flex-shrink-0"
      style={{ width: 220, background: COLORS.sidebar, borderRight: `1px solid ${COLORS.border}` }}
    >
      <div>
        <div className="flex items-center justify-between gap-2.5 px-5 py-4">
          <div className="flex items-center gap-2.5">
            <div
              className="flex items-center justify-center rounded-md font-bold text-white flex-shrink-0"
              style={{ width: 30, height: 30, background: "linear-gradient(135deg, #2563eb, #0891b2)", fontFamily: "inherit" }}
            >
              F
            </div>
            <div className="text-sm font-semibold leading-tight" style={{ color: COLORS.text }}>
              Data Ingestion<br />Engine
            </div>
          </div>

          {/* Removed close button; sidebar controlled only by header hamburger */}
        </div>

        <nav className="mt-2 px-3" aria-label="Sidebar navigation">
          {NAV_ITEMS.map(({ key, label, icon: Icon }) => {
            const active = page === key;
            return (
              <div
                key={key}
                onClick={() => goTo(key)}
                className="flex items-center gap-3 px-3 py-2.5 rounded-md cursor-pointer text-sm mb-1"
                style={{
                  background: active ? COLORS.blueSoft : "transparent",
                  color: active ? COLORS.blue : COLORS.textMuted,
                  fontWeight: active ? 600 : 500,
                }}
              >
                <Icon size={17} strokeWidth={2} />
                {label}
              </div>
            );
          })}
        </nav>
      </div>

      <div className="px-4 py-4" style={{ borderTop: `1px solid ${COLORS.border}` }}>
        <div className="flex items-center gap-2.5">
          <div
            className="flex items-center justify-center rounded-full text-white text-xs font-semibold flex-shrink-0"
            style={{ width: 32, height: 32, background: COLORS.blue }}
          >
            {initials}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-semibold truncate" style={{ color: COLORS.text }}>{displayName}</div>
            <div className="text-xs truncate" style={{ color: COLORS.textFaint }}>{user ? "Signed in" : "guest"}</div>
          </div>
        </div>

        <div className="mt-3">
          <button onClick={onSignOut} className="w-full text-left text-sm text-red-600 hover:underline">Sign out</button>
        </div>
      </div>
    </div>
  );
}

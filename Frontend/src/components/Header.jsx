import React from "react";
import { Menu, Bell, Settings, Moon, Sun } from "lucide-react";
import { COLORS } from "../theme";

// The top header bar provides the app title actions and the menu button for the sidebar.
export default function Header({
  notificationCount = 3,
  onToggleSidebar,
  onOpenSettings = () => {},
  themeMode = "light",
  onToggleTheme = () => {},
  jiraPolling = false,
}) {
  return (
    <div
      className="flex shrink-0 items-center justify-between px-4 md:px-6"
      style={{
        height: 56,
        background: COLORS.header,
        borderBottom: `1px solid ${COLORS.border}`,
      }}
    >
      <button
        type="button"
        onClick={onToggleSidebar}
        className="rounded-md p-2 transition-colors hover:bg-slate-100"
        aria-label="Toggle sidebar navigation"
      >
        <Menu size={20} style={{ color: COLORS.textMuted }} />
      </button>

      <div className="flex items-center gap-4">
        {jiraPolling && (
          <div
            className="flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold"
            style={{ background: "#dcfce7", color: "#16a34a" }}
          >
            <span
              className="inline-block w-2 h-2 rounded-full animate-pulse"
              style={{ background: "#16a34a" }}
            />
            Jira polling
          </div>
        )}
        <button
          type="button"
          onClick={onToggleTheme}
          className="rounded-md p-2 transition-colors hover:bg-slate-100"
          aria-label="Toggle dark mode"
        >
          {themeMode === "dark" ? (
            <Sun size={18} style={{ color: COLORS.textMuted }} />
          ) : (
            <Moon size={18} style={{ color: COLORS.textMuted }} />
          )}
        </button>
        <div className="relative cursor-pointer">
          <Bell size={19} style={{ color: COLORS.textMuted }} />
          {notificationCount > 0 && (
            <span
              className="absolute flex items-center justify-center text-white rounded-full"
              style={{
                top: -6,
                right: -7,
                width: 16,
                height: 16,
                fontSize: 10,
                background: COLORS.blue,
                fontWeight: 600,
              }}
            >
              {notificationCount}
            </span>
          )}
        </div>
        <Settings
          size={19}
          style={{ color: COLORS.textMuted }}
          className="cursor-pointer"
          onClick={onOpenSettings}
        />
      </div>
    </div>
  );
}

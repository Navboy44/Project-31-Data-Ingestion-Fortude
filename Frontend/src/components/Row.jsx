import React from "react";
import { COLORS } from "../theme";

export default function Row({
  label,
  sub,
  onEdit,
  onDelete,
  roundedActions = false,
}) {
  return (
    <div
      className="flex flex-wrap items-center justify-between gap-3 px-5 py-3"
      style={{ borderBottom: `1px solid ${COLORS.borderSoft}` }}
    >
      <div>
        <span className="text-sm" style={{ color: COLORS.text }}>
          {label}
        </span>
        {sub && (
          <span className="text-xs ml-2" style={{ color: COLORS.textFaint }}>
            {sub}
          </span>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {onEdit && (
          <button
            onClick={onEdit}
            className={
              roundedActions
                ? "config-button config-button-primary"
                : "text-sm bg-transparent border-none cursor-pointer font-medium"
            }
            style={roundedActions ? undefined : { color: COLORS.blue }}
          >
            Edit
          </button>
        )}
        {onDelete && (
          <button
            onClick={onDelete}
            className={
              roundedActions
                ? "config-button config-button-danger"
                : "text-sm bg-transparent border-none cursor-pointer font-medium"
            }
            style={roundedActions ? undefined : { color: COLORS.red }}
          >
            Delete
          </button>
        )}
      </div>
    </div>
  );
}

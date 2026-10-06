import React from "react";
import { COLORS } from "../theme";

export default function PageHeading({ title, subtitle }) {
  return (
    <div className="mb-5">
      <h1
        className="font-bold m-0 mb-1.5"
        style={{ color: COLORS.text, fontSize: 28, letterSpacing: "-0.01em" }}
      >
        {title}
      </h1>
      <p className="m-0" style={{ color: COLORS.textMuted, fontSize: 15 }}>
        {subtitle}
      </p>
    </div>
  );
}

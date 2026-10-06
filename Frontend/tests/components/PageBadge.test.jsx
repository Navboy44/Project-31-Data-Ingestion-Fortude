/**
 * Unit tests for the `PageBadge` component (src/components/PageBadge.jsx).
 *
 * `PageBadge` is a tiny presentational component that renders whichever
 * page-label string it is given at the top of the app. The only behaviour
 * worth verifying is that the `label` prop is rendered as-is.
 */
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import PageBadge from "../../src/components/PageBadge";

describe("PageBadge", () => {
  // checks if the PageBadge component renders the supplied label text
  it("renders the supplied label text", () => {
    render(<PageBadge label="Dashboard Page" />);
    expect(screen.getByText("Dashboard Page")).toBeInTheDocument();
  });
// checks if the PageBadge component renders a different label when props change
  it("renders a different label when props change", () => {
    const { rerender } = render(<PageBadge label="Dashboard Page" />);
    expect(screen.getByText("Dashboard Page")).toBeInTheDocument();

    rerender(<PageBadge label="History Page" />);
    expect(screen.queryByText("Dashboard Page")).not.toBeInTheDocument();
    expect(screen.getByText("History Page")).toBeInTheDocument();
  });
});

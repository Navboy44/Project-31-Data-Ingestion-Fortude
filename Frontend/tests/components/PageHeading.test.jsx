/**
 * Unit tests for the `PageHeading` component (src/components/PageHeading.jsx).
 *
 * `PageHeading` renders a page's <h1> title and a supporting subtitle
 * paragraph. This is a pure presentational component, so the tests simply
 * confirm both pieces of text are rendered in the correct elements.
 */
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import PageHeading from "../../src/components/PageHeading";

describe("PageHeading", () => {
  // checks if the PageHeading component renders the title as a heading and the subtitle as supporting text
  it("renders the title as a heading and the subtitle as supporting text", () => {
    render(<PageHeading title="Configuration" subtitle="Manage connectors, rules, and output targets." />);

    expect(screen.getByRole("heading", { name: "Configuration" })).toBeInTheDocument();
    expect(screen.getByText("Manage connectors, rules, and output targets.")).toBeInTheDocument();
  });
});

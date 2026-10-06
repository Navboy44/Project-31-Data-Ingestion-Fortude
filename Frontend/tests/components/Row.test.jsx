/**
 * Unit tests for the `Row` component (src/components/Row.jsx).
 *
 * `Row` renders a single labelled list item (used for connectors, rules,
 * outputs, and history entries) with optional "Edit" and "Delete" actions.
 * The action buttons should only appear when a corresponding handler prop
 * is supplied, and clicking them should invoke that handler.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import Row from "../../src/components/Row";

describe("Row", () => {
  // checks if the Row component renders the label and optional sub-label text
  it("renders the label and optional sub-label text", () => {
    render(<Row label="Infor Sales" sub="(connector)" />);

    expect(screen.getByText("Infor Sales")).toBeInTheDocument();
    expect(screen.getByText("(connector)")).toBeInTheDocument();
  });
// checks if the Row component omits the sub-label when it is not supplied
  it("omits the sub-label when it is not supplied", () => {
    render(<Row label="Infor Sales" />);
    expect(screen.queryByText("(connector)")).not.toBeInTheDocument();
  });
//checks if the Row component hides the Edit/Delete buttons when their handlers are not provided
  it("hides Edit/Delete buttons when their handlers are not provided", () => {
    render(<Row label="Infor Sales" />);

    expect(screen.queryByRole("button", { name: /edit/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /delete/i })).not.toBeInTheDocument();
  });
//checks if the Row component shows the Edit/Delete buttons and calls the right handler when clicked
  it("shows Edit/Delete buttons and calls the right handler when clicked", async () => {
    const user = userEvent.setup();
    const onEdit = vi.fn();
    const onDelete = vi.fn();

    render(<Row label="Infor Sales" onEdit={onEdit} onDelete={onDelete} />);

    await user.click(screen.getByRole("button", { name: /edit/i }));
    expect(onEdit).toHaveBeenCalledTimes(1);
    expect(onDelete).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: /delete/i }));
    expect(onDelete).toHaveBeenCalledTimes(1);
  });
});

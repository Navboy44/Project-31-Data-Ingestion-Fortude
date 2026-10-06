/**
 * Unit tests for the `History` page (src/pages/History.jsx).
 *
 * `History` renders every past ingestion run, most recent first (the
 * component reverses the `history` array before rendering), and exposes
 * "View" and "Delete" actions per row. These tests verify the display
 * order, the zero-padded ID formatting, and that the row action buttons
 * call back with the correct entry id.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import History from "../../src/pages/History";

const HISTORY = [
  { id: 1, connector: "Infor Sales" },
  { id: 2, connector: "Jira Support" },
  { id: 3, connector: "SharePoint KB" },
];

describe("History", () => {

  //checks if the History page renders entries in reverse order (most recent first)/
  it("renders entries in reverse (most recent first) order", () => {
    render(<History history={HISTORY} openEntry={() => {}} deleteEntry={() => {}} />);

    const entryLabels = screen.getAllByText(/^Entry \d/).map((el) => el.textContent);
    expect(entryLabels[0]).toMatch(/^Entry 3/);
    expect(entryLabels[1]).toMatch(/^Entry 2/);
    expect(entryLabels[2]).toMatch(/^Entry 1/);
  });

  //checks if the History page zero-pads the entry id in the ID column/
  it("zero-pads the entry id in the ID column", () => {
    render(<History history={HISTORY} openEntry={() => {}} deleteEntry={() => {}} />);
    expect(screen.getByText("#001")).toBeInTheDocument();
    expect(screen.getByText("#002")).toBeInTheDocument();
    expect(screen.getByText("#003")).toBeInTheDocument();
  });

  //checks if the History page renders no rows when the history array is empty/
  it("renders no rows when history is empty", () => {
    render(<History history={[]} openEntry={() => {}} deleteEntry={() => {}} />);
    // "Entry" alone still appears as the table's column header, so assert
    // on the more specific "Entry <id>" row text instead.
    expect(screen.queryByText(/^Entry \d/)).not.toBeInTheDocument();
  });

  //checks if the History page calls openEntry with the clicked row's id when View is clicked/
  it("calls openEntry with the clicked row's id when View is clicked", async () => {
    const user = userEvent.setup();
    const openEntry = vi.fn();

    render(<History history={HISTORY} openEntry={openEntry} deleteEntry={() => {}} />);

    // Rows render most-recent-first, so the first "View" button belongs to entry 3.
    const viewButtons = screen.getAllByRole("button", { name: "View" });
    await user.click(viewButtons[0]);

    expect(openEntry).toHaveBeenCalledWith(3);
  });

  //checks if the History page calls deleteEntry with the clicked row's id when Delete is clicked/
  it("calls deleteEntry with the clicked row's id when Delete is clicked", async () => {
    const user = userEvent.setup();
    const deleteEntry = vi.fn();

    render(<History history={HISTORY} openEntry={() => {}} deleteEntry={deleteEntry} />);

    const deleteButtons = screen.getAllByRole("button", { name: "Delete" });
    await user.click(deleteButtons[1]); // second row shown is entry 2

    expect(deleteEntry).toHaveBeenCalledWith(2);
  });
});

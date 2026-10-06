/**
 * Unit tests for the `Sidebar` component (src/components/Sidebar.jsx).
 *
 * `Sidebar` renders the main navigation links plus a user profile summary.
 * It contains a small but important piece of pure logic: deriving a
 * two-letter "initials" badge from the `user` prop. These tests cover:
 *   - Navigation clicks call `goTo` with the right page key.
 *   - The "Sign out" button calls `onSignOut`.
 *   - The initials/display-name logic for guests, single-word names, and
 *     multi-word names.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import Sidebar from "../../src/components/Sidebar";

describe("Sidebar", () => {
  //checks if the Sidebar component calls goTo with the clicked page's key
  it("calls goTo with the clicked page's key", async () => {
    const user = userEvent.setup();
    const goTo = vi.fn();

    render(<Sidebar page="dashboard" goTo={goTo} />);

    await user.click(screen.getByText("History"));
    expect(goTo).toHaveBeenCalledWith("history");
  });
//checks if the Sidebar component calls onSignOut when the sign-out button is clicked
  it("calls onSignOut when the sign-out button is clicked", async () => {
    const user = userEvent.setup();
    const onSignOut = vi.fn();

    render(<Sidebar page="dashboard" goTo={() => {}} onSignOut={onSignOut} />);

    await user.click(screen.getByRole("button", { name: /sign out/i }));
    expect(onSignOut).toHaveBeenCalledTimes(1);
  });
//checks if the Sidebar component falls back to a guest name and initials when no user is signed in
  it("falls back to a guest name and 'AS' initials when no user is signed in", () => {
    render(<Sidebar page="dashboard" goTo={() => {}} user={null} />);

    expect(screen.getByText("Amanda Smith")).toBeInTheDocument();
    expect(screen.getByText("AS")).toBeInTheDocument();
    expect(screen.getByText("guest")).toBeInTheDocument();
  });
//checks if the Sidebar component derives initials from the first two letters of a single-word username
  it("derives initials from the first two letters of a single-word username", () => {
    render(<Sidebar page="dashboard" goTo={() => {}} user="alice" />);

    expect(screen.getByText("alice")).toBeInTheDocument();
    expect(screen.getByText("AL")).toBeInTheDocument();
    expect(screen.getByText("Signed in")).toBeInTheDocument();
  });
//checks if the Sidebar component derives initials from the first letter of each word for a full name
  it("derives initials from the first letter of each word for a full name", () => {
    render(<Sidebar page="dashboard" goTo={() => {}} user="Jane Doe" />);

    expect(screen.getByText("Jane Doe")).toBeInTheDocument();
    expect(screen.getByText("JD")).toBeInTheDocument();
  });
//checks if the Sidebar component highlights the active page differently from inactive ones
  it("highlights the active page differently from inactive ones", () => {
    render(<Sidebar page="history" goTo={() => {}} />);

    // Active items are rendered with font-weight 600, inactive ones with 500.
    const activeItem = screen.getByText("History").closest("div");
    const inactiveItem = screen.getByText("Dashboard").closest("div");

    expect(activeItem).toHaveStyle({ fontWeight: 600 });
    expect(inactiveItem).toHaveStyle({ fontWeight: 500 });
  });
});

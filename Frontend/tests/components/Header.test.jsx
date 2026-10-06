/**
 * Unit tests for the `Header` component (src/components/Header.jsx).
 *
 * `Header` renders the top app bar: a sidebar toggle button, a dark-mode
 * toggle, a notification bell with an unread count badge, a settings icon,
 * and an optional "Jira polling" indicator. These tests exercise the
 * callback props and the conditional rendering driven by `themeMode`,
 * `notificationCount`, and `jiraPolling`.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import Header from "../../src/components/Header";

//checks if the Header component renders correctly and calls the appropriate callback functions 

describe("Header", () => {
  it("calls onToggleSidebar when the menu button is clicked", async () => {
    const user = userEvent.setup();
    const onToggleSidebar = vi.fn();

    render(<Header onToggleSidebar={onToggleSidebar} />);

    await user.click(screen.getByRole("button", { name: /toggle sidebar navigation/i }));
    expect(onToggleSidebar).toHaveBeenCalledTimes(1);
  });
// checks if the Header component calls the onToggleTheme callback when the theme button is clicked
  it("calls onToggleTheme when the theme button is clicked", async () => {
    const user = userEvent.setup();
    const onToggleTheme = vi.fn();

    render(<Header onToggleSidebar={() => {}} onToggleTheme={onToggleTheme} themeMode="light" />);

    await user.click(screen.getByRole("button", { name: /toggle dark mode/i }));
    expect(onToggleTheme).toHaveBeenCalledTimes(1);
  });

  // checks if the Header component calls the onOpenSettings callback when the settings icon is clicked

  it("calls onOpenSettings when the settings icon is clicked", async () => {
    const user = userEvent.setup();
    const onOpenSettings = vi.fn();

    render(<Header onToggleSidebar={() => {}} onOpenSettings={onOpenSettings} />);

    // The settings icon is an <svg>, not a <button>, so it's queried by
    // test id via lucide-react's rendered element role of "img"-less svg —
    // instead we find it through its parent container class using a query
    // for the whole header and simulate the click on the icon via role.
    const settingsIcon = document.querySelector("svg.cursor-pointer");
    expect(settingsIcon).not.toBeNull();
    await user.click(settingsIcon);
    expect(onOpenSettings).toHaveBeenCalledTimes(1);
  });

// checks if the Header component shows the notification count badge only when count is greater than zero  
  it("shows the notification count badge only when count is greater than zero", () => {
    const { rerender } = render(<Header onToggleSidebar={() => {}} notificationCount={5} />);
    expect(screen.getByText("5")).toBeInTheDocument();

    rerender(<Header onToggleSidebar={() => {}} notificationCount={0} />);
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  // checks if the Header component shows the Jira polling indicator only when jiraPolling is true
  it("shows the Jira polling indicator only when jiraPolling is true", () => {
    const { rerender } = render(<Header onToggleSidebar={() => {}} jiraPolling={false} />);
    expect(screen.queryByText(/jira polling/i)).not.toBeInTheDocument();

    rerender(<Header onToggleSidebar={() => {}} jiraPolling={true} />);
    expect(screen.getByText(/jira polling/i)).toBeInTheDocument();
  });
});

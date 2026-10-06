/**
 * Unit tests for the `ChangeUsername` page (src/pages/ChangeUsername.jsx).
 *
 * This page validates its form client-side before ever calling the
 * backend: both the current password and the new username are required,
 * and submitting a complete form opens a confirmation dialog rather than
 * immediately saving. Only confirming that dialog triggers the network
 * request. These tests verify the validation messages, the confirmation
 * step, and the resulting `fetch` call / callbacks — with `fetch` mocked
 * so no real network activity occurs.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, afterEach } from "vitest";
import ChangeUsername from "../../src/pages/ChangeUsername";

// The "New username" / "Current password" labels aren't associated with
// their inputs via htmlFor/id, so we locate them the same way as the
// Login page tests: by role for the plain text input, and by DOM query
// for the password input.

//checks if the ChangeUsername page renders the username and password input fields
function getFormInputs(container) {
  return {
    usernameInput: screen.getByRole("textbox"),
    passwordInput: container.querySelector('input[type="password"]'),
  };
}
// Mocks a fetch response with the given body and ok status.
function mockJsonResponse(body, { ok = true } = {}) {
  return { ok, json: () => Promise.resolve(body) };
}
//checks if the ChangeUsername page renders the form validation messages 
describe("ChangeUsername", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });
  
  // checks if the ChangeUsername page requires the current password before allowing submission
  it("requires the current password before allowing submission", async () => {
    const user = userEvent.setup();
    const { container } = render(<ChangeUsername token="t" currentUser="alice" goTo={() => {}} />);
    const { usernameInput } = getFormInputs(container);

    await user.type(usernameInput, "newname");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(screen.getByText("Please enter your current password to confirm.")).toBeInTheDocument();
    // No confirmation dialog should appear until validation passes.
    expect(screen.queryByRole("button", { name: "Confirm" })).not.toBeInTheDocument();
  });
  
  // checks if the ChangeUsername page requires a new username before allowing submission
  it("requires a new username before allowing submission", async () => {
    const user = userEvent.setup();
    const { container } = render(<ChangeUsername token="t" currentUser="alice" goTo={() => {}} />);
    const { passwordInput } = getFormInputs(container);

    await user.type(passwordInput, "hunter2");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(screen.getByText("Please enter a new username.")).toBeInTheDocument();
  });

  
  //checks if the ChangeUsername page requires both fields to be filled in before allowing submission
  it("opens a confirmation dialog once both fields are filled in", async () => {
    const user = userEvent.setup();
    const { container } = render(<ChangeUsername token="t" currentUser="alice" goTo={() => {}} />);
    const { usernameInput, passwordInput } = getFormInputs(container);

    await user.type(usernameInput, "bob");
    await user.type(passwordInput, "hunter2");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(screen.getByText(/are you sure you want to change your username to/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirm" })).toBeInTheDocument();
  });

  // checks if cancelling the confirmation dialog closes it without saving
  it("cancelling the confirmation dialog closes it without saving", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const { container } = render(<ChangeUsername token="t" currentUser="alice" goTo={() => {}} />);
    const { usernameInput, passwordInput } = getFormInputs(container);

    await user.type(usernameInput, "bob");
    await user.type(passwordInput, "hunter2");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("button", { name: "Confirm" })).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  //checks if confirming the change submits the change, reports the new username, and navigates back to settings
  it("confirming submits the change, reports the new username, and navigates back to settings", async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    const goTo = vi.fn();

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(mockJsonResponse({ username: "bob" }))
    );

    const { container } = render(
      <ChangeUsername token="t" currentUser="alice" goTo={goTo} onSaved={onSaved} />
    );
    const { usernameInput, passwordInput } = getFormInputs(container);

    await user.type(usernameInput, "bob");
    await user.type(passwordInput, "hunter2");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await user.click(screen.getByRole("button", { name: "Confirm" }));

    expect(await screen.findByText("Saved")).toBeInTheDocument();
    expect(onSaved).toHaveBeenCalledWith("bob");
    expect(goTo).toHaveBeenCalledWith("settings");
  });

  //checks if the ChangeUsername page shows the server's error message when the change request fails
  it("shows the server's error message when the change request fails", async () => {
    const user = userEvent.setup();

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(mockJsonResponse({ detail: "Incorrect password" }, { ok: false }))
    );

    const { container } = render(<ChangeUsername token="t" currentUser="alice" goTo={() => {}} />);
    const { usernameInput, passwordInput } = getFormInputs(container);

    await user.type(usernameInput, "bob");
    await user.type(passwordInput, "wrong");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await user.click(screen.getByRole("button", { name: "Confirm" }));

    expect(await screen.findByText("Incorrect password")).toBeInTheDocument();
  });
});

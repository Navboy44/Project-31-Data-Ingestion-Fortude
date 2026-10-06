/**
 * Unit tests for the `Login` page (src/pages/Login.jsx).
 *
 * `Login` renders a sign-in/register form and talks to the backend via
 * `fetch`. Because these are frontend-only unit tests, every network call
 * is mocked with `vi.stubGlobal("fetch", ...)` rather than hitting a real
 * server — this lets us test the component's behaviour (state transitions,
 * error handling, localStorage writes) in isolation.
 *
 * Covered behaviour:
 *   - Toggling between "Sign in" and "Create account" modes.
 *   - A successful login stores the token and calls `onLogin`.
 *   - A failed login (non-OK response) surfaces the server's error message.
 *   - A network failure (fetch throws) surfaces a generic "Network error".
 *   - A response with `mfa_required: true` swaps in the `Mfa` sub-component.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import Login from "../../src/pages/Login";

// Builds a minimal mock `Response`-like object for `fetch` to resolve with.
function mockJsonResponse(body, { ok = true } = {}) {
  return {
    ok,
    json: () => Promise.resolve(body),
  };
}

// The username/password <label> elements in Login.jsx are not associated
// with their <input>s via `htmlFor`/`id`, so `getByLabelText` can't find
// them. Instead we grab the username input by its implicit "textbox" role
// (it's the only plain text input on the form) and the password input via
// a direct DOM query, since password inputs have no accessible role.
function getFormInputs(container) {
  return {
    usernameInput: screen.getByRole("textbox"),
    passwordInput: container.querySelector('input[type="password"]'),
  };
}

describe("Login", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  //checks if the Login page renders the sign-in form by default
  it("renders the sign-in form by default", () => {
    render(<Login onLogin={() => {}} />);

    expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  //checks if the Login page toggles to the register form and back
  it("toggles to the register form and back", async () => {
    const user = userEvent.setup();
    render(<Login onLogin={() => {}} />);

    await user.click(screen.getByRole("button", { name: /create account/i }));
    expect(screen.getByRole("heading", { name: "Create account" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /have an account\? sign in/i }));
    expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });

  //checks if the Login page lets the user type into the username and password fields
  it("lets the user type into the username and password fields", async () => {
    const user = userEvent.setup();
    const { container } = render(<Login onLogin={() => {}} />);
    const { usernameInput, passwordInput } = getFormInputs(container);

    await user.type(usernameInput, "alice");
    await user.type(passwordInput, "hunter2");

    expect(usernameInput).toHaveValue("alice");
    expect(passwordInput).toHaveValue("hunter2");
  });

  //checks if the Login page stores the token and calls onLogin with the username on a successful login
  it("on a successful login, stores the token and calls onLogin with the username", async () => {
    const user = userEvent.setup();
    const onLogin = vi.fn();

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(mockJsonResponse({ token: "abc123", username: "alice" }))
    );

    const { container } = render(<Login onLogin={onLogin} />);
    const { usernameInput, passwordInput } = getFormInputs(container);

    await user.type(usernameInput, "alice");
    await user.type(passwordInput, "hunter2");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(onLogin).toHaveBeenCalledWith("alice");
    expect(localStorage.getItem("auth_token")).toBe("abc123");
  });

  //checks if the Login page shows the server-provided error message when login fails
  it("shows the server-provided error message when login fails", async () => {
    const user = userEvent.setup();

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(mockJsonResponse({ detail: "Invalid credentials" }, { ok: false }))
    );

    const { container } = render(<Login onLogin={() => {}} />);
    const { usernameInput, passwordInput } = getFormInputs(container);

    await user.type(usernameInput, "alice");
    await user.type(passwordInput, "wrong");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("Invalid credentials")).toBeInTheDocument();
  });

  //checks if the Login page shows a generic network error message when fetch throws an exception
  it("shows a generic network error message when fetch throws", async () => {
    const user = userEvent.setup();

    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("boom")));

    const { container } = render(<Login onLogin={() => {}} />);
    const { usernameInput, passwordInput } = getFormInputs(container);

    await user.type(usernameInput, "alice");
    await user.type(passwordInput, "hunter2");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("Network error")).toBeInTheDocument();
  });

  //checks if the Login page switches to the MFA screen when the server responds with mfa_required: true
  it("switches to the MFA screen when the server requires a second factor", async () => {
    const user = userEvent.setup();

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(mockJsonResponse({ mfa_required: true, tmp_token: "tmp-1" }))
    );

    const { container } = render(<Login onLogin={() => {}} />);
    const { usernameInput, passwordInput } = getFormInputs(container);

    await user.type(usernameInput, "alice");
    await user.type(passwordInput, "hunter2");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("heading", { name: "Enter MFA code" })).toBeInTheDocument();
  });
});

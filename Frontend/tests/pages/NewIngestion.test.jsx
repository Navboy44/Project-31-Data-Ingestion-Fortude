/**
 * Unit tests for the `NewIngestion` page (src/pages/NewIngestion.jsx).
 *
 * `NewIngestion` renders a four-field form (connector, mapper, rules,
 * outputs) and only enables the "Start" button once every field has a
 * value. Submitting calls the `onStart` prop, which can report failures
 * through the `onError` callback it receives; the page then swaps to a
 * dedicated loading or error screen. These tests use a fully-populated,
 * in-memory `config` object and a controlled `form`/`setForm` pair so the
 * component can be driven the same way the real `App` drives it.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { useState } from "react";
import NewIngestion from "../../src/pages/NewIngestion";

const CONFIG = {
  connectors: [{ id: 1, name: "Infor Sales" }],
  rules: [{ id: 1, name: "Infor Sales Rules" }],
  outputs: [{ id: 1, name: "PostgreSQL" }],
};

// `NewIngestion` expects its `form` state to be lifted up by the parent
// (as `App` does). This small wrapper reproduces that contract in tests so
// user interactions actually update the values the component reads.
function Wrapper({ onStart }) {
  const [form, setForm] = useState({ connector: "", mapper: "", rules: "", outputs: "" });
  return <NewIngestion form={form} setForm={setForm} config={CONFIG} onStart={onStart} />;
}

describe("NewIngestion", () => {
  //checks if the NewIngestion page disables the Start button until every field has a value/
  it("disables the Start button until every field has a value", async () => {
    const user = userEvent.setup();
    render(<Wrapper onStart={vi.fn()} />);

    const startButton = screen.getByRole("button", { name: "Start" });
    expect(startButton).toBeDisabled();

    await user.selectOptions(screen.getByLabelText("Select Connector"), "Infor Sales");
    await user.selectOptions(screen.getByLabelText("Select Mapper"), "Standard Field Mapper");
    await user.selectOptions(screen.getByLabelText("Select Rules"), "Infor Sales Rules");
    expect(startButton).toBeDisabled(); // outputs still unset

    await user.selectOptions(screen.getByLabelText("Select Outputs"), "PostgreSQL");
    expect(startButton).toBeEnabled();
  });

  //checks if the NewIngestion page shows a loading screen while onStart is pending, naming the chosen connector/
  it("shows a loading screen while onStart is pending, naming the chosen connector", async () => {
    const user = userEvent.setup();
    // onStart never resolves during this test, so the component stays in
    // the "loading" state, letting us assert on the spinner screen.
    const onStart = vi.fn(() => new Promise(() => {}));

    render(<Wrapper onStart={onStart} />);

    await user.selectOptions(screen.getByLabelText("Select Connector"), "Infor Sales");
    await user.selectOptions(screen.getByLabelText("Select Mapper"), "Standard Field Mapper");
    await user.selectOptions(screen.getByLabelText("Select Rules"), "Infor Sales Rules");
    await user.selectOptions(screen.getByLabelText("Select Outputs"), "PostgreSQL");

    await user.click(screen.getByRole("button", { name: "Start" }));

    expect(screen.getByText(/running ingestion/i)).toBeInTheDocument();
    expect(screen.getByText("Infor Sales")).toBeInTheDocument();
    expect(onStart).toHaveBeenCalledTimes(1);
  });

  //checks if the NewIngestion page shows the error screen with the reported message when onStart reports an error/
  it("shows the error screen with the reported message when onStart reports an error", async () => {
    const user = userEvent.setup();
    // Mirrors how App.startIngestion invokes options.onError on failure.
    const onStart = vi.fn(({ onError }) => {
      onError("Ingestion request failed");
      return Promise.resolve();
    });

    render(<Wrapper onStart={onStart} />);

    await user.selectOptions(screen.getByLabelText("Select Connector"), "Infor Sales");
    await user.selectOptions(screen.getByLabelText("Select Mapper"), "Standard Field Mapper");
    await user.selectOptions(screen.getByLabelText("Select Rules"), "Infor Sales Rules");
    await user.selectOptions(screen.getByLabelText("Select Outputs"), "PostgreSQL");
    await user.click(screen.getByRole("button", { name: "Start" }));

    expect(await screen.findByText("Ingestion could not complete")).toBeInTheDocument();
    expect(screen.getByText("Ingestion request failed")).toBeInTheDocument();
  });

  //checks if the NewIngestion page lets the user go back to the form after an error  
  it("lets the user go back to the form after an error", async () => {
    const user = userEvent.setup();
    const onStart = vi.fn(({ onError }) => {
      onError("boom");
      return Promise.resolve();
    });

    render(<Wrapper onStart={onStart} />);

    await user.selectOptions(screen.getByLabelText("Select Connector"), "Infor Sales");
    await user.selectOptions(screen.getByLabelText("Select Mapper"), "Standard Field Mapper");
    await user.selectOptions(screen.getByLabelText("Select Rules"), "Infor Sales Rules");
    await user.selectOptions(screen.getByLabelText("Select Outputs"), "PostgreSQL");
    await user.click(screen.getByRole("button", { name: "Start" }));

    await user.click(await screen.findByRole("button", { name: /go back & retry/i }));

    expect(screen.getByText("New Data Ingestion")).toBeInTheDocument();
  });
});

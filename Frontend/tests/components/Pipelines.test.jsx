import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import Pipelines from "../../src/components/Pipelines";
const CONFIG = {
  connectors: [{ id: 2, name: "Jira" }],
  rules: [
    { id: 2, name: "L3 Ticket Rules" },
    { id: 3, name: "Knowledge Base Rules" },
  ],
  outputs: [
    { id: 1, name: "MongoDB" },
    { id: 3, name: "Kafka" },
  ],
};

// sample pipeline for testing
const PIPELINE = {
  id: 10,
  name: "Test Pipeline",
  connector: CONFIG.connectors[0],
  rules: CONFIG.rules,
  outputs: CONFIG.outputs,
};

describe("Pipelines", () => {
  // The first click only asks for confirmation, cancel does not change the list
  it("cancels deletion without calling onDelete", async () => {
    const user = userEvent.setup();
    const onDelete = vi.fn();
    render(
      <Pipelines config={CONFIG} pipelines={[PIPELINE]} onDelete={onDelete} />
    );
    await user.click(
      screen.getByRole("button", { name: "Delete Test Pipeline" })
    );
    expect(
      screen.getByRole("region", { name: "Confirm pipeline deletion" })
    ).toHaveTextContent('Delete pipeline "Test Pipeline"?');
    expect(onDelete).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(
      screen.queryByRole("region", { name: "Confirm pipeline deletion" })
    ).not.toBeInTheDocument();
    expect(screen.getByText("Test Pipeline")).toBeInTheDocument();
    expect(onDelete).not.toHaveBeenCalled();
  });

  // Only the confirmed pipeline ID is sent to App; controls lock during deletion.
  it("deletes the confirmed pipeline and waits for completion", async () => {
    const user = userEvent.setup();
    let finishDelete;
    const onDelete = vi.fn(
      () =>
        new Promise((resolve) => {
          finishDelete = resolve;
        })
    );
    const { rerender } = render(
      <Pipelines config={CONFIG} pipelines={[PIPELINE]} onDelete={onDelete} />
    );
    await user.click(
      screen.getByRole("button", { name: "Delete Test Pipeline" })
    );
    await user.click(screen.getByRole("button", { name: "Confirm delete" }));
    expect(onDelete).toHaveBeenCalledWith(10);
    expect(screen.getByRole("button", { name: "Deleting..." })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    finishDelete();
    expect(await screen.findByRole("status")).toHaveTextContent(
      'Pipeline "Test Pipeline" deleted.'
    );
    // App supplies the list after the successful request.
    rerender(<Pipelines config={CONFIG} pipelines={[]} onDelete={onDelete} />);
    expect(screen.getByText("No saved pipelines yet.")).toBeInTheDocument();
  });

  // A failed request keeps the row and allows the same deletion to be retried.
  it("keeps the pipeline when deletion fails", async () => {
    const user = userEvent.setup();
    const onDelete = vi
      .fn()
      .mockRejectedValueOnce(new Error("Unable to delete"));
    render(
      <Pipelines config={CONFIG} pipelines={[PIPELINE]} onDelete={onDelete} />
    );
    await user.click(
      screen.getByRole("button", { name: "Delete Test Pipeline" })
    );
    await user.click(screen.getByRole("button", { name: "Confirm delete" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Unable to delete"
    );
    expect(screen.getByText("Test Pipeline")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Confirm delete" })
    ).toBeEnabled();
    onDelete.mockResolvedValueOnce();
    await user.click(screen.getByRole("button", { name: "Confirm delete" }));
    expect(await screen.findByRole("status")).toHaveTextContent("deleted");
  });

  it("displays loading and then the pipelines supplied by App", () => {
    const { rerender } = render(<Pipelines config={CONFIG} loading />);
    expect(screen.getByText(/Loading pipelines/)).toBeInTheDocument();
    rerender(<Pipelines config={CONFIG} pipelines={[PIPELINE]} />);
    expect(screen.getByText("Test Pipeline")).toBeInTheDocument();
    expect(screen.getByText("Connector: Jira")).toBeInTheDocument();
    expect(screen.getByText("Outputs: MongoDB, Kafka")).toBeInTheDocument();
  });

  // Save requires a name and at least one of each reference type.
  it("disables Save until the required values are selected", async () => {
    const user = userEvent.setup();
    render(<Pipelines config={CONFIG} />);
    await user.click(screen.getByRole("button", { name: "Create pipeline" }));
    const save = screen.getByRole("button", { name: "Save pipeline" });
    expect(save).toBeDisabled();
    await user.type(screen.getByLabelText("Pipeline name"), "   ");
    await user.selectOptions(screen.getByLabelText("Connector"), "2");
    await user.click(screen.getByLabelText("L3 Ticket Rules"));
    await user.click(screen.getByLabelText("Kafka"));
    expect(save).toBeDisabled();
    await user.type(screen.getByLabelText("Pipeline name"), "Test Pipeline");
    expect(save).toBeEnabled();
  });

  // Creating passes a trimmed name and numeric IDs to the parent callback.
  it("sends a new definition to onCreate", async () => {
    const user = userEvent.setup();
    const onCreate = vi.fn().mockResolvedValue(PIPELINE);
    render(<Pipelines config={CONFIG} onCreate={onCreate} />);
    await user.click(screen.getByRole("button", { name: "Create pipeline" }));
    await user.type(screen.getByLabelText("Pipeline name"), " Test Pipeline ");
    await user.selectOptions(screen.getByLabelText("Connector"), "2");
    await user.click(screen.getByLabelText("L3 Ticket Rules"));
    await user.click(screen.getByLabelText("Knowledge Base Rules"));
    await user.click(screen.getByLabelText("MongoDB"));
    await user.click(screen.getByLabelText("Kafka"));
    await user.click(screen.getByRole("button", { name: "Save pipeline" }));
    expect(onCreate).toHaveBeenCalledWith({
      name: "Test Pipeline",
      connector_id: 2,
      rule_ids: [2, 3],
      output_ids: [1, 3],
    });
    expect(screen.queryByRole("form")).not.toBeInTheDocument();
  });

  // Editing reads expanded references and sends the existing ID separately.
  it("prefills an edit and sends the changes to onUpdate", async () => {
    const user = userEvent.setup();
    const onUpdate = vi
      .fn()
      .mockResolvedValue({ ...PIPELINE, name: "Updated" });
    render(
      <Pipelines config={CONFIG} pipelines={[PIPELINE]} onUpdate={onUpdate} />
    );
    await user.click(
      screen.getByRole("button", { name: "Edit Test Pipeline" })
    );
    expect(screen.getByLabelText("Pipeline name")).toHaveValue("Test Pipeline");
    expect(screen.getByLabelText("Connector")).toHaveValue("2");
    expect(screen.getByLabelText("Kafka")).toBeChecked();
    await user.clear(screen.getByLabelText("Pipeline name"));
    await user.type(screen.getByLabelText("Pipeline name"), "Updated");
    await user.click(screen.getByLabelText("MongoDB"));
    await user.click(screen.getByRole("button", { name: "Save pipeline" }));
    expect(onUpdate).toHaveBeenCalledWith(10, {
      name: "Updated",
      connector_id: 2,
      rule_ids: [2, 3],
      output_ids: [3],
    });
    expect(screen.queryByRole("form")).not.toBeInTheDocument();
  });

  // Parent request errors stay visible without clearing the draft.
  it("preserves the draft when saving fails", async () => {
    const user = userEvent.setup();
    const onUpdate = vi
      .fn()
      .mockRejectedValue(new Error("Pipeline already exists"));
    render(
      <Pipelines config={CONFIG} pipelines={[PIPELINE]} onUpdate={onUpdate} />
    );
    await user.click(
      screen.getByRole("button", { name: "Edit Test Pipeline" })
    );
    await user.click(screen.getByRole("button", { name: "Save pipeline" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Pipeline already exists"
    );
    expect(screen.getByLabelText("Pipeline name")).toHaveValue("Test Pipeline");
    expect(screen.getByLabelText("Kafka")).toBeChecked();
  });

  // Cancel resets editing state without making a save request.
  it("cancels an edit and opens an empty create form", async () => {
    const user = userEvent.setup();
    const onUpdate = vi.fn();
    render(
      <Pipelines config={CONFIG} pipelines={[PIPELINE]} onUpdate={onUpdate} />
    );
    await user.click(
      screen.getByRole("button", { name: "Edit Test Pipeline" })
    );
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await user.click(screen.getByRole("button", { name: "Create pipeline" }));
    expect(screen.getByLabelText("Pipeline name")).toHaveValue("");
    expect(screen.getByLabelText("Kafka")).not.toBeChecked();
    expect(onUpdate).not.toHaveBeenCalled();
  });

  // App decides how to reload; the component just requests a retry.
  it("shows a loading error and calls onRetry", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(
      <Pipelines
        config={CONFIG}
        loadError="Unable to load pipelines"
        onRetry={onRetry}
      />
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Unable to load pipelines"
    );
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});

/**
 * Unit tests for the `Select` component (src/components/Select.jsx).
 *
 * `Select` is a thin wrapper around a native <select> element used by the
 * "New Ingestion" form to pick a connector, mapper, rules, or output. These
 * tests check that:
 *   - The placeholder renders as the first, empty-valued option.
 *   - Every option in the `options` array renders as a selectable choice.
 *   - Selecting a new value fires the `onChange` callback.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import Select from "../../src/components/Select";

describe("Select", () => {
  const options = ["Infor Sales", "Jira Support", "SharePoint KB"];
//checks if the Select component renders the placeholder as the first option
  it("renders the placeholder as the first option", () => {
    render(<Select value="" onChange={() => {}} options={options} placeholder="Choose one" />);

    const placeholderOption = screen.getByRole("option", { name: "Choose one" });
    expect(placeholderOption).toBeInTheDocument();
    expect(placeholderOption.value).toBe("");
  });
//checks if the Select component renders every supplied option
  it("renders every supplied option", () => {
    render(<Select value="" onChange={() => {}} options={options} placeholder="Choose one" />);

    options.forEach((label) => {
      expect(screen.getByRole("option", { name: label })).toBeInTheDocument();
    });

    // placeholder + 3 real options
    expect(screen.getAllByRole("option")).toHaveLength(options.length + 1);
  });
//checks if the Select component reflects the currently selected value
  it("reflects the currently selected value", () => {
    render(<Select value="Jira Support" onChange={() => {}} options={options} placeholder="Choose one" />);

    expect(screen.getByRole("combobox").value).toBe("Jira Support");
  });
//checks if the Select component calls onChange when a different option is selected
  it("calls onChange when the user picks a different option", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();

    render(<Select value="" onChange={onChange} options={options} placeholder="Choose one" />);

    await user.selectOptions(screen.getByRole("combobox"), "SharePoint KB");
    expect(onChange).toHaveBeenCalledTimes(1);
  });
});

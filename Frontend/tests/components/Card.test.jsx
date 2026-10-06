/**
 * Unit tests for the `Card` component (src/components/Card.jsx).
 *
 * `Card` is a purely presentational container used across the dashboard and
 * configuration pages. It is responsible for:
 *   - Rendering a title and an optional numeric "count" badge.
 *   - Rendering arbitrary children inside its body.
 *   - Optionally rendering a clickable footer that fires a callback.
 *
 * These tests verify that rendering logic in isolation, without needing a
 * running backend or the rest of the app.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import Card from "../../src/components/Card";

describe("Card", () => {
  //checks if the Card component renders the title and its children correctly
  it("renders the title and its children", () => {
    render(
      <Card title="Connectors">
        <div>child content</div>
      </Card>
    );

    expect(screen.getByText("Connectors")).toBeInTheDocument();
    expect(screen.getByText("child content")).toBeInTheDocument();
  });
//checks if the Card component does not render a count badge when `count` is not supplied
  it("does not render a count badge when `count` is not supplied", () => {
    render(<Card title="Connectors">content</Card>);

    // The badge renders whatever value is passed as `count`; if the prop is
    // omitted it should not render a badge element at all.
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });
//checks if the Card component renders the count badge when `count` is supplied, including zero
  it("renders the count badge when `count` is supplied, including zero", () => {
    render(
      <Card title="Connectors" count={0}>
        content
      </Card>
    );

    // even when the count is 0 it must render the badge, since the user may want to see that there are no items
    expect(screen.getByText("0")).toBeInTheDocument();
  });
// checks if the Card component renders a footer and calls the onFooterClick callback when the footer is clicked
  it("renders a footer and calls onFooterClick when the footer is clicked", async () => {
    const user = userEvent.setup();
    const onFooterClick = vi.fn();

    render(
      <Card title="Connectors" footer="+ Add Connector" onFooterClick={onFooterClick}>
        content
      </Card>
    );

    const footer = screen.getByText("+ Add Connector");
    expect(footer).toBeInTheDocument();

    await user.click(footer);
    expect(onFooterClick).toHaveBeenCalledTimes(1);
  });
// checks if the Card component does not render a footer section when the footer prop is not supplied
  it("does not render a footer section when `footer` is not supplied", () => {
    render(<Card title="Connectors">content</Card>);
    expect(screen.queryByText(/add/i)).not.toBeInTheDocument();
  });
});

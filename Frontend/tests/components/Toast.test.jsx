/**
 * Unit tests for the `Toast` component (src/components/Toast.jsx).
 *
 * `Toast` always renders the same DOM node, but toggles its visibility
 * (opacity/transform) based on whether a `message` string was supplied.
 * These tests confirm the message text renders and that the visibility
 * styling responds correctly to an empty vs. non-empty message.
 */
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import Toast from "../../src/components/Toast";

describe("Toast", () => {
  //checks if the Toast component renders the provided message text
  it("renders the provided message text", () => {
    render(<Toast message="Entry 3 deleted" />);
    expect(screen.getByText("Entry 3 deleted")).toBeInTheDocument();
  });
//checks if the Toast component is visually hidden (opacity 0) when there is no message
  it("is visually hidden (opacity 0) when there is no message", () => {
    const { container } = render(<Toast message="" />);
    // The toast <div> is the sole top-level element this component renders.
    expect(container.firstChild).toHaveStyle({ opacity: 0 });
  });
//checks if the Toast component is visually shown (opacity 1) when a message is present
  it("is visually shown (opacity 1) when a message is present", () => {
    render(<Toast message="Saved" />);
    expect(screen.getByText("Saved")).toHaveStyle({ opacity: 1 });
  });
});

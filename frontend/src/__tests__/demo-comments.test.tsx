import { beforeEach, describe, expect, it, mock } from "bun:test";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import CommentThread from "@/components/demo/CommentThread";
import DecisionView from "@/components/demo/DecisionView";
import { MOCK_STEPS } from "@/lib/demo/mock";
import type { ReviewThread } from "@/lib/demo/types";

const decision = MOCK_STEPS[0].decisions[0];

function makeThread(overrides: Partial<ReviewThread> = {}): ReviewThread {
  return {
    decision_id: decision.decision_id,
    resolution: "open",
    comments: [],
    ...overrides,
  };
}

const existingComment = {
  comment_id: "c-1",
  author: "Raul",
  body: "Looks off to me",
  created_at: "2026-01-01T10:00:00Z",
};

function renderView(thread?: ReviewThread) {
  const onAddComment = mock();
  const onResolve = mock();
  render(
    <DecisionView
      decision={decision}
      thread={thread}
      parents={[]}
      onAddComment={onAddComment}
      onResolve={onResolve}
      onOpenParent={mock()}
    />,
  );
  return { onAddComment, onResolve };
}

describe("DecisionView comments", () => {
  beforeEach(() => {
    mock.restore();
  });

  it("shows the evidence quote and page", () => {
    renderView();
    const evidence = decision.evidence[0];
    expect(screen.getByText(evidence.quote)).toBeInTheDocument();
    expect(screen.getAllByText(`p. ${evidence.page}`).length).toBeGreaterThan(
      0,
    );
  });

  it("disables Comment for empty or whitespace and trims on submit", async () => {
    const user = userEvent.setup();
    const { onAddComment } = renderView();
    const button = screen.getByRole("button", { name: "Comment" });
    expect(button).toBeDisabled();

    const box = screen.getByRole("textbox", { name: "Add a comment" });
    await user.type(box, "   ");
    expect(button).toBeDisabled();

    await user.type(box, " hello  ");
    await user.click(button);
    expect(onAddComment).toHaveBeenCalledWith("hello");
  });

  it("disables Reject until the thread has a comment", () => {
    const { unmount } = render(
      <CommentThread
        decisionId="d"
        thread={undefined}
        onAddComment={mock()}
        onResolve={mock()}
      />,
    );
    expect(screen.getByRole("button", { name: "Reject" })).toBeDisabled();
    expect(
      screen.getByText("Add a comment explaining why"),
    ).toBeInTheDocument();
    unmount();

    renderView(makeThread({ comments: [existingComment] }));
    expect(screen.getByText("Looks off to me")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reject" })).toBeEnabled();
  });

  it("resolves as accepted and rejected", async () => {
    const user = userEvent.setup();
    const { onResolve } = renderView(
      makeThread({ comments: [existingComment] }),
    );
    await user.click(screen.getByRole("button", { name: "Accept suggestion" }));
    expect(onResolve).toHaveBeenCalledWith("accepted");
    await user.click(screen.getByRole("button", { name: "Reject" }));
    expect(onResolve).toHaveBeenCalledWith("rejected");
  });

  it("shows a pill and Reopen for a resolved thread", async () => {
    const user = userEvent.setup();
    const { onResolve } = renderView(
      makeThread({ resolution: "accepted", comments: [existingComment] }),
    );
    expect(screen.getByText("Accepted")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reopen" }));
    expect(onResolve).toHaveBeenCalledWith("open");
  });

  it("keeps reasoning collapsed until expanded", async () => {
    const user = userEvent.setup();
    renderView();
    const firstStep = decision.trace[0].text;
    expect(screen.queryByText(firstStep, { exact: false })).toBeNull();
    await user.click(
      screen.getByRole("button", {
        name: `Show reasoning (${decision.trace.length} steps)`,
      }),
    );
    expect(screen.getByText(firstStep, { exact: false })).toBeInTheDocument();
  });
});

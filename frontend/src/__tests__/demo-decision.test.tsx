import { describe, expect, it, mock } from "bun:test";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import DecisionView from "@/components/demo/DecisionView";
import { MOCK_STEPS } from "@/lib/demo/mock";
import type { Decision } from "@/lib/demo/types";

const ingestDecision = MOCK_STEPS[0].decisions[0];

function renderView(decision: Decision = ingestDecision) {
  const onOpenParent = mock();
  render(
    <DecisionView
      decision={decision}
      parents={[]}
      onOpenParent={onOpenParent}
    />
  );
  return { onOpenParent };
}

describe("DecisionView agent output", () => {
  it("accepts a protocol comparison option and can decline it", async () => {
    const user = userEvent.setup();
    const decision = MOCK_STEPS[2].decisions.find((item) =>
      item.options?.some((option) => option.proposed_change));
    if (!decision) throw new Error("Expected a peer recommendation");
    const option = decision.options!.find((item) => item.proposed_change)!;
    const onReview = mock();
    render(<DecisionView decision={decision} parents={[]}
      onOpenParent={mock()} onReview={onReview} />);
    await user.click(screen.getByRole("button", {
      name: `Accept ${option.title}`,
    }));
    expect(onReview).toHaveBeenCalledWith("accepted", option.option_id);
    await user.click(screen.getByRole("button", {
      name: `Decline ${option.title}`,
    }));
    expect(onReview).toHaveBeenCalledWith("rejected", option.option_id);
  });

  it("keeps direct acceptance available alongside informational options",
    async () => {
      const user = userEvent.setup();
      const source = MOCK_STEPS[2].decisions.find((item) =>
        item.proposed_change);
      if (!source) throw new Error("Expected a proposed peer change");
      const decision = { ...source, options: [{
        option_id: "context", title: "Discuss with investigator",
        rationale: "Informational context only",
      }] };
      const onReview = mock();
      render(<DecisionView decision={decision} parents={[]}
        onOpenParent={mock()} onReview={onReview} />);
      await user.click(screen.getByRole("button", {
        name: "Accept recommendation",
      }));
      expect(onReview).toHaveBeenCalledWith("accepted");
      expect(screen.queryByRole("button", {
        name: "Accept Discuss with investigator",
      })).toBeNull();
    });

  it("shows the evidence quote and page", () => {
    renderView();
    const evidence = ingestDecision.evidence[0];
    expect(screen.getByText(evidence.quote)).toBeInTheDocument();
    expect(
      screen.getAllByText(new RegExp(`p\\. ${evidence.page}`)).length
    ).toBeGreaterThan(0);
  });

  it("keeps reasoning collapsed until expanded, citing its sources", async () => {
    const user = userEvent.setup();
    renderView();
    const firstStep = ingestDecision.trace[0].text;
    expect(screen.queryByText(firstStep, { exact: false })).toBeNull();

    await user.click(
      screen.getByRole("button", { name: "Expand" })
    );
    expect(
      screen.getByText(firstStep, { exact: false })
    ).toBeInTheDocument();
    expect(screen.getByText("(Ingestion · p. 24)")).toBeInTheDocument();
  });

  it("offers no review actions, only agent output", () => {
    renderView();
    for (const name of [/Accept/, /Reject/, /Dismiss/, /Comment/]) {
      expect(screen.queryByRole("button", { name })).toBeNull();
    }
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  it("jumps to an earlier finding it builds on", async () => {
    const user = userEvent.setup();
    const onOpenParent = mock();
    const peersDecision = MOCK_STEPS[2].decisions[0];
    render(
      <DecisionView
        decision={peersDecision}
        parents={[
          { decision_id: "d-ing-01", title: "Eligibility criteria extracted" },
        ]}
        onOpenParent={onOpenParent}
      />
    );

    await user.click(
      screen.getByRole("button", { name: "Eligibility criteria extracted" })
    );
    expect(onOpenParent).toHaveBeenCalledWith("d-ing-01");
  });
});

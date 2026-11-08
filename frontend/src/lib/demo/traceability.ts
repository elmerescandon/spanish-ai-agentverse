import type { StepData } from "./types";

// Keeps overviews scannable: a step shows at most this many figures.
export const MAX_STEP_METRICS = 4;

/**
 * Walk every decision and report broken links in the traceability chain.
 * Returns human-readable errors; an empty list means the chain is intact.
 */
export function findTraceabilityErrors(
  steps: readonly StepData[],
  protocolPageCount: number
): string[] {
  const errors: string[] = [];
  const seenDecisionIds = new Set<string>();

  for (const step of steps) {
    if (step.metrics.length > MAX_STEP_METRICS) {
      errors.push(
        `step ${step.id} has ${step.metrics.length} metrics, ` +
          `expected at most ${MAX_STEP_METRICS}`
      );
    }

    for (const decision of step.decisions) {
      const where = `decision ${decision.decision_id}`;

      if (decision.step_id !== step.id) {
        errors.push(
          `${where} sits in step ${step.id} but declares ` +
            `${decision.step_id}`
        );
      }
      if (decision.evidence.length === 0) {
        errors.push(`${where} has no evidence`);
      }

      const evidenceIds = new Set(decision.evidence.map((e) => e.evidence_id));
      for (const entry of decision.trace) {
        for (const evidenceId of entry.evidence_ids) {
          if (!evidenceIds.has(evidenceId)) {
            errors.push(
              `${where} trace cites unknown evidence ${evidenceId}`
            );
          }
        }
      }

      for (const evidence of decision.evidence) {
        const isProtocolPage =
          evidence.source === "protocol" && evidence.page !== null;
        if (
          isProtocolPage &&
          (evidence.page! < 1 || evidence.page! > protocolPageCount)
        ) {
          errors.push(
            `${where} cites page ${evidence.page}, expected 1-` +
              `${protocolPageCount}`
          );
        }
      }

      for (const parentId of decision.derived_from ?? []) {
        if (!seenDecisionIds.has(parentId)) {
          errors.push(
            `${where} derives from ${parentId}, which is not in an ` +
              `earlier step or decision`
          );
        }
      }

      seenDecisionIds.add(decision.decision_id);
    }
  }

  return errors;
}

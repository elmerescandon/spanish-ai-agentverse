"use client";

import { useState } from "react";
import type { ReviewStatus } from "@/lib/demo/types";

export default function ReviewActions({ status, onReview }: {
  status: ReviewStatus;
  onReview: (status: ReviewStatus, comment: string) => void;
}) {
  const [comment, setComment] = useState("");
  return (
    <section className="rounded-xl bg-zinc-50 p-5 space-y-3">
      <h3 className="font-serif text-lg">Your clinical decision</h3>
      <p className="text-sm text-zinc-500">
        Decisions are held in this session and included in your download.
        Accepting records approval; it does not rewrite the source PDF.
      </p>
      <label className="block text-sm">
        Review note (required to decline)
        <textarea
          value={comment}
          onChange={(event) => setComment(event.target.value)}
          className="mt-2 block w-full rounded-lg border bg-white p-3"
          placeholder="Explain your clinical decision…"
        />
      </label>
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" className="review-primary"
          onClick={() => onReview("accepted", comment)}>
          Accept suggestion
        </button>
        <button type="button" className="review-secondary"
          disabled={!comment.trim()}
          onClick={() => onReview("rejected", comment)}>
          Decline suggestion
        </button>
        <span key={status} role="status" className="review-card text-sm">
          {status === "pending" ? "Awaiting your review" :
            status === "accepted" ? "✓ Accepted" : "Declined"}
        </span>
      </div>
    </section>
  );
}

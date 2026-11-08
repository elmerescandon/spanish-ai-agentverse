"use client";

import { useState } from "react";
import { Check, X } from "lucide-react";
import type {
  ReviewComment,
  ReviewResolution,
  ReviewThread,
} from "@/lib/demo/types";

export interface CommentThreadProps {
  decisionId: string;
  thread: ReviewThread | undefined;
  onAddComment: (body: string) => void;
  onResolve: (resolution: ReviewResolution) => void;
}

function formatTime(createdAt: string): string {
  const date = new Date(createdAt);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function CommentItem({ comment }: { comment: ReviewComment }) {
  return (
    <li className="flex gap-2.5">
      <span
        aria-hidden
        className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-emerald-100 font-sans text-xs font-medium text-emerald-800"
      >
        {comment.author.charAt(0).toUpperCase()}
      </span>
      <div className="min-w-0 space-y-0.5">
        <p className="font-sans text-xs text-zinc-500">
          <span className="font-medium text-zinc-900">{comment.author}</span>{" "}
          {formatTime(comment.created_at)}
        </p>
        <p className="whitespace-pre-wrap break-words font-sans text-sm text-zinc-800">
          {comment.body}
        </p>
      </div>
    </li>
  );
}

/** Margin comment card: comments plus accept / reject for one finding. */
export default function CommentThread({
  decisionId,
  thread,
  onAddComment,
  onResolve,
}: CommentThreadProps) {
  const [draft, setDraft] = useState("");
  const body = draft.trim();
  const comments = thread?.comments ?? [];
  const resolution = thread?.resolution ?? "open";
  const inputId = `comment-${decisionId}`;

  function submit() {
    if (body === "") return;
    onAddComment(body);
    setDraft("");
  }

  return (
    <section
      aria-label="Comments"
      className="space-y-4 rounded-xl border border-zinc-200 bg-white p-4"
    >
      <div className="flex items-center justify-between">
        <h2 className="font-sans text-xs font-semibold uppercase tracking-wider text-zinc-500">
          Comments
        </h2>
        {resolution !== "open" && (
          <div className="flex items-center gap-2">
            <span
              className={`rounded-full px-2 py-0.5 font-sans text-xs font-medium ${
                resolution === "accepted"
                  ? "bg-emerald-50 text-emerald-700"
                  : "bg-zinc-100 text-zinc-700"
              }`}
            >
              {resolution === "accepted" ? "Accepted" : "Rejected"}
            </span>
            <button
              type="button"
              onClick={() => onResolve("open")}
              className="cursor-pointer font-sans text-xs text-zinc-600 underline underline-offset-4 hover:text-emerald-700"
            >
              Reopen
            </button>
          </div>
        )}
      </div>

      {comments.length > 0 && (
        <ul className="animate-file-change space-y-3">
          {comments.map((comment) => (
            <CommentItem key={comment.comment_id} comment={comment} />
          ))}
        </ul>
      )}

      <div className="space-y-2">
        <label htmlFor={inputId} className="sr-only">
          Add a comment
        </label>
        <textarea
          id={inputId}
          aria-label="Add a comment"
          placeholder="Add a comment"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          rows={2}
          className="w-full resize-none rounded-lg border border-zinc-200 bg-white p-2.5 font-sans text-sm text-zinc-900 outline-none focus:border-emerald-500"
        />
        <button
          type="button"
          disabled={body === ""}
          onClick={submit}
          className="cursor-pointer rounded-full bg-emerald-600 px-4 py-1.5 font-sans text-xs font-medium text-white transition-colors hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Comment
        </button>
      </div>

      {resolution === "open" && (
        <div className="space-y-2 border-t border-zinc-200/60 pt-3">
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => onResolve("accepted")}
              className="inline-flex cursor-pointer items-center gap-1.5 rounded-full border border-emerald-200 px-3 py-1.5 font-sans text-xs font-medium text-emerald-700 transition-colors hover:bg-emerald-50"
            >
              <Check className="h-3.5 w-3.5" strokeWidth={1.5} aria-hidden />
              Accept suggestion
            </button>
            <button
              type="button"
              disabled={comments.length === 0}
              onClick={() => onResolve("rejected")}
              className="inline-flex cursor-pointer items-center gap-1.5 rounded-full border border-zinc-200 px-3 py-1.5 font-sans text-xs font-medium text-zinc-700 transition-colors hover:bg-zinc-50 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <X className="h-3.5 w-3.5" strokeWidth={1.5} aria-hidden />
              Reject
            </button>
          </div>
          {comments.length === 0 && (
            <p className="font-sans text-xs text-zinc-500">
              Add a comment explaining why
            </p>
          )}
        </div>
      )}
    </section>
  );
}

import { afterEach, beforeEach, describe, expect, it, mock } from "bun:test";
import { act, render, screen, waitFor } from "@testing-library/react";
import { LogoIntro } from "@/components/logo-intro";
import {
  INTRO_DECISION_SCRIPT,
  INTRO_PLAY_ATTRIBUTE,
  INTRO_SEEN_KEY,
} from "@/lib/logo-intro";

interface FakeWindowOptions {
  pathname?: string;
  prefersReducedMotion?: boolean;
  seenBefore?: boolean;
}

// Runs the exact script text the layout puts in <head>, against a window
// whose path, storage and motion preference the test controls.
function runDecisionScript({
  pathname = "/",
  prefersReducedMotion = false,
  seenBefore = false,
}: FakeWindowOptions = {}): Map<string, string> {
  const storage = new Map<string, string>(
    seenBefore ? [[INTRO_SEEN_KEY, "1"]] : []
  );
  const fakeWindow = {
    location: { pathname },
    sessionStorage: {
      getItem: (key: string) => storage.get(key) ?? null,
      setItem: (key: string, value: string) => storage.set(key, value),
    },
    matchMedia: (query: string) => ({
      matches: prefersReducedMotion && query.includes("reduce"),
    }),
    document,
  };
  new Function("window", INTRO_DECISION_SCRIPT)(fakeWindow);
  return storage;
}

// jsdom has no AnimationEvent, so React listens for the prefixed
// webkitAnimationEnd there; real browsers fire animationend.
function endAnimation(element: Element): void {
  act(() => {
    element.dispatchEvent(new Event("webkitAnimationEnd", { bubbles: true }));
  });
}

const isMarkedToPlay = () =>
  document.documentElement.hasAttribute(INTRO_PLAY_ATTRIBUTE);

describe("Homepage logo intro", () => {
  beforeEach(() => {
    mock.restore();
    document.documentElement.removeAttribute(INTRO_PLAY_ATTRIBUTE);
  });

  afterEach(() => {
    document.documentElement.removeAttribute(INTRO_PLAY_ATTRIBUTE);
  });

  it("plays on the first homepage visit of the session", () => {
    const storage = runDecisionScript();

    expect(isMarkedToPlay()).toBe(true);
    expect(storage.get(INTRO_SEEN_KEY)).toBe("1");
  });

  it("does not play again in the same session", () => {
    runDecisionScript({ seenBefore: true });

    expect(isMarkedToPlay()).toBe(false);
  });

  it("does not play for visitors who prefer reduced motion", () => {
    runDecisionScript({ prefersReducedMotion: true });

    expect(isMarkedToPlay()).toBe(false);
  });

  it("does not play on other pages", () => {
    const storage = runDecisionScript({ pathname: "/demo" });

    expect(isMarkedToPlay()).toBe(false);
    expect(storage.has(INTRO_SEEN_KEY)).toBe(false);
  });

  it("shows the cover and removes it when the cover fade ends", async () => {
    document.documentElement.setAttribute(INTRO_PLAY_ATTRIBUTE, "");
    render(<LogoIntro />);
    const cover = screen.getByTestId("logo-intro");

    // The molecule's own animations finishing must not end the intro.
    endAnimation(cover.querySelector("svg") as SVGElement);
    expect(screen.getByTestId("logo-intro")).toBeInTheDocument();

    endAnimation(cover);
    expect(isMarkedToPlay()).toBe(false);
    await waitFor(() =>
      expect(screen.queryByTestId("logo-intro")).not.toBeInTheDocument()
    );
  });

  it("removes itself at once when the intro should not play", () => {
    render(<LogoIntro />);

    expect(screen.queryByTestId("logo-intro")).not.toBeInTheDocument();
  });
});

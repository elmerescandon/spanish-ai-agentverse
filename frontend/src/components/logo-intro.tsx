"use client";

import { type AnimationEvent, useSyncExternalStore } from "react";
import { InsulinIcon } from "@/components/insulin-icon";
import { INTRO_PLAY_ATTRIBUTE } from "@/lib/logo-intro";

function subscribeToPlayMark(onChange: () => void): () => void {
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, {
    attributeFilter: [INTRO_PLAY_ATTRIBUTE],
  });
  return () => observer.disconnect();
}

const isMarkedToPlay = () =>
  document.documentElement.hasAttribute(INTRO_PLAY_ATTRIBUTE);

// The server can't know the visitor's session, so the cover is always in
// the HTML; CSS hides it unless the <head> script marked the page.
const isMarkedOnServer = () => true;

/**
 * First-visit intro: over a blurred view of the page, the insulin molecule
 * forms (each chain revealed left to right), then fades as the blur clears,
 * bringing the page into focus. It follows the <head> script's mark on
 * <html>, and clearing the mark when the unblur ends removes it.
 */
export function LogoIntro() {
  const isPlaying = useSyncExternalStore(
    subscribeToPlayMark,
    isMarkedToPlay,
    isMarkedOnServer
  );

  if (!isPlaying) return null;

  const finish = (event: AnimationEvent<HTMLDivElement>) => {
    // The windows' and molecule's animations bubble up; only the cover's
    // unblur ends the intro.
    if (event.target !== event.currentTarget) return;
    document.documentElement.removeAttribute(INTRO_PLAY_ATTRIBUTE);
  };

  return (
    <div
      className="logo-intro"
      data-testid="logo-intro"
      aria-hidden="true"
      onAnimationEnd={finish}
    >
      <div className="logo-intro-molecule">
        {/* Each chain sits in a window that slides open left to right. */}
        <span className="logo-intro-window logo-intro-window-top">
          <span className="logo-intro-content">
            <InsulinIcon className="logo-intro-icon" />
          </span>
        </span>
        <span className="logo-intro-window logo-intro-window-bottom">
          <span className="logo-intro-content">
            <InsulinIcon className="logo-intro-icon" />
          </span>
        </span>
      </div>
    </div>
  );
}

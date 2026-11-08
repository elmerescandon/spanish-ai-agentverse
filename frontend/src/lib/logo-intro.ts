// The homepage intro plays once per browser session. Whether it plays is
// decided by a tiny script in <head> before the first paint, so a first
// visit never glimpses the page before the cover and a repeat visit never
// sees the cover flash. The script marks <html> with INTRO_PLAY_ATTRIBUTE;
// CSS shows the cover only while that attribute is there.

export const INTRO_SEEN_KEY = "protocolai-intro-seen";
export const INTRO_PLAY_ATTRIBUTE = "data-intro-play";

type IntroWindow = Pick<
  Window,
  "location" | "sessionStorage" | "matchMedia" | "document"
>;

// Inlined into the page as source text, so it must only use its
// parameters: no imports, no outer constants.
export function decideIntro(
  win: IntroWindow,
  seenKey: string,
  playAttribute: string
): void {
  try {
    if (win.location.pathname !== "/") return;
    if (win.sessionStorage.getItem(seenKey) !== null) return;
    if (win.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    win.sessionStorage.setItem(seenKey, "1");
    win.document.documentElement.setAttribute(playAttribute, "");
  } catch {
    // Storage can be blocked (e.g. strict privacy settings); the page
    // then simply shows without the intro.
  }
}

export const INTRO_DECISION_SCRIPT = `(${decideIntro.toString()})(window, ${JSON.stringify(
  INTRO_SEEN_KEY
)}, ${JSON.stringify(INTRO_PLAY_ATTRIBUTE)});`;

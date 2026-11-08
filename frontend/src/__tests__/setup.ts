import { afterEach, expect, mock } from "bun:test";
import type { TestingLibraryMatchers } from "@testing-library/jest-dom/matchers";
import { JSDOM } from "jsdom";

declare module "bun:test" {
  // eslint-disable-next-line @typescript-eslint/no-empty-object-type
  interface Matchers<T>
    extends TestingLibraryMatchers<typeof expect.stringContaining, T> {}
}

const dom = new JSDOM("<!doctype html><html><body></body></html>", {
  url: "http://localhost:3000",
});

class MockResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

class MockIntersectionObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords() {
    return [];
  }
}

const mockMatchMedia = (query: string) => ({
  matches: false,
  media: query,
  onchange: null,
  addListener: () => {},
  removeListener: () => {},
  addEventListener: () => {},
  removeEventListener: () => {},
  dispatchEvent: () => false,
});

// jsdom has no animation frames; run the callback on the next tick.
const mockRequestAnimationFrame = (callback: FrameRequestCallback) =>
  setTimeout(() => callback(performance.now()), 0) as unknown as number;
const mockCancelAnimationFrame = (handle: number) => clearTimeout(handle);

Object.assign(globalThis, {
  window: dom.window,
  document: dom.window.document,
  navigator: dom.window.navigator,
  HTMLElement: dom.window.HTMLElement,
  SVGElement: dom.window.SVGElement,
  Element: dom.window.Element,
  Node: dom.window.Node,
  Text: dom.window.Text,
  DocumentFragment: dom.window.DocumentFragment,
  Event: dom.window.Event,
  MouseEvent: dom.window.MouseEvent,
  KeyboardEvent: dom.window.KeyboardEvent,
  CustomEvent: dom.window.CustomEvent,
  MutationObserver: dom.window.MutationObserver,
  ResizeObserver: MockResizeObserver,
  IntersectionObserver: MockIntersectionObserver,
  requestAnimationFrame: mockRequestAnimationFrame,
  cancelAnimationFrame: mockCancelAnimationFrame,
  matchMedia: mockMatchMedia,
  getComputedStyle: dom.window.getComputedStyle.bind(dom.window),
  IS_REACT_ACT_ENVIRONMENT: true,
});

Object.assign(dom.window, {
  ResizeObserver: MockResizeObserver,
  IntersectionObserver: MockIntersectionObserver,
  requestAnimationFrame: mockRequestAnimationFrame,
  cancelAnimationFrame: mockCancelAnimationFrame,
  matchMedia: mockMatchMedia,
});

if (!globalThis.URL.createObjectURL) {
  globalThis.URL.createObjectURL = () => "blob:http://localhost:3000/mock-blob";
}
if (!globalThis.URL.revokeObjectURL) {
  globalThis.URL.revokeObjectURL = () => {};
}

// Default Next.js App Router navigation mocks so components using routing hooks render cleanly
mock.module("next/navigation", () => ({
  useRouter: () => ({
    push: () => {},
    replace: () => {},
    prefetch: () => {},
    back: () => {},
    forward: () => {},
    refresh: () => {},
  }),
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({}),
}));

const matchers = await import("@testing-library/jest-dom/matchers");
const { cleanup } = await import("@testing-library/react");

expect.extend(matchers as unknown as Parameters<typeof expect.extend>[0]);

afterEach(() => {
  cleanup();
});

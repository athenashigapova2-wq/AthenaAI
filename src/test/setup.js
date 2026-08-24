import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

globalThis.ResizeObserver ??= ResizeObserverMock;
globalThis.HTMLElement.prototype.scrollIntoView ??= () => {};
globalThis.HTMLElement.prototype.hasPointerCapture ??= () => false;
globalThis.HTMLElement.prototype.setPointerCapture ??= () => {};
globalThis.HTMLElement.prototype.releasePointerCapture ??= () => {};

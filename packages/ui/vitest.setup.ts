import "@testing-library/jest-dom/vitest";

// jsdom has no ResizeObserver; Radix popper-based components (tooltip) need one.
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

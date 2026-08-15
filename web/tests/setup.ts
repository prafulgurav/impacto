import '@testing-library/jest-dom/vitest';

// jsdom implements neither of these, and both are used by the chart components
// and the offline banner respectively.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver;

Object.defineProperty(navigator, 'onLine', { value: true, writable: true });

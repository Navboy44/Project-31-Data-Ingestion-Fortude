

// Extends expect() with DOM matchers like toBeInTheDocument(), toHaveStyle(), toBeDisabled().
import "@testing-library/jest-dom";

import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

// Node ships its own built-in `localStorage` global, which shadows jsdom's
// working implementation but is broken in this sandboxed environment
//Login and ChangeUsername call localStorage directly, so we swap in a small working in-memory replacement.
class MemoryLocalStorage {
  #store = new Map();

  getItem(key) {
    return this.#store.has(key) ? this.#store.get(key) : null;
  }

  setItem(key, value) {
    this.#store.set(key, String(value));
  }

  removeItem(key) {
    this.#store.delete(key);
  }

  clear() {
    this.#store.clear();
  }
}

const memoryLocalStorage = new MemoryLocalStorage();

// Override both forms of the global since app code may reference either.
Object.defineProperty(globalThis, "localStorage", {
  value: memoryLocalStorage,
  configurable: true,
  writable: true,
});
Object.defineProperty(window, "localStorage", {
  value: memoryLocalStorage,
  configurable: true,
  writable: true,
});

// Unmount rendered components and reset storage so tests can't leak state into each other.
afterEach(() => {
  cleanup();
  memoryLocalStorage.clear();
});

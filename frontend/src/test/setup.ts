// Vitest global setup — runs once before the test suite.
// Adds @testing-library/jest-dom matchers (toBeInTheDocument, toHaveClass, …)
// and cleans up the rendered React tree after every test so cases stay
// isolated.
import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, beforeEach } from 'vitest'

// jsdom's window.localStorage is not reliably present under newer Node
// versions (Node >=22 ships its own experimental global localStorage that
// shadows jsdom's, but stays undefined without --localstorage-file). Install a
// small in-memory Storage polyfill so component/client code that reads or
// writes localStorage works identically on every Node version and in CI.
class MemoryStorage implements Storage {
  private store = new Map<string, string>()
  get length() {
    return this.store.size
  }
  clear() {
    this.store.clear()
  }
  getItem(key: string) {
    return this.store.has(key) ? this.store.get(key)! : null
  }
  key(index: number) {
    return Array.from(this.store.keys())[index] ?? null
  }
  removeItem(key: string) {
    this.store.delete(key)
  }
  setItem(key: string, value: string) {
    this.store.set(key, String(value))
  }
}

function installStorage(name: 'localStorage' | 'sessionStorage') {
  Object.defineProperty(globalThis, name, {
    value: new MemoryStorage(),
    configurable: true,
    writable: true,
  })
}

installStorage('localStorage')
installStorage('sessionStorage')

beforeEach(() => {
  localStorage.clear()
  sessionStorage.clear()
})

afterEach(() => {
  cleanup()
})

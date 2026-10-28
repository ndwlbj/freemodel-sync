/**
 * Minimal ambient declaration for the host-provided React runtime.
 *
 * This is deliberately not `@types/react`: the plugin must not add React as a
 * dependency, and the compiled browser bundle keeps `require("react")` as an
 * external supplied by `window.__ModuleLoader__`.
 */
declare module "react" {
  import type { ReactElementLike } from "./react-runtime.ts";

  export const Fragment: unknown;
  export function createElement(type: unknown, props?: Record<string, unknown> | null, ...children: unknown[]): ReactElementLike;
  export function useState<T>(initial: T | (() => T)): [T, (next: T | ((previous: T) => T)) => void];
  export function useEffect(effect: () => void | (() => void), deps?: readonly unknown[]): void;
  export function useCallback<T extends (...args: never[]) => unknown>(callback: T, deps: readonly unknown[]): T;
  export function useMemo<T>(factory: () => T, deps: readonly unknown[]): T;
}
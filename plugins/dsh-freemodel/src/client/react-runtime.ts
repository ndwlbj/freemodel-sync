/**
 * The tiny React surface this card uses.
 *
 * The browser bundle does not depend on `react`: the host loader hands it the
 * runtime through `require("react")`, and `entry.ts` installs that runtime
 * here. Keeping the types local means the plugin adds no React package (and
 * no second copy of it) to the profile.
 */

/** A rendered element, as React's `createElement` returns it. */
export interface ReactElementLike {
  readonly type: unknown;
  readonly props: Record<string, unknown>;
}

/** A function component's shape; hooks are read from {@link ReactLike}. */
export type ComponentLike<P> = (props: P) => ReactElementLike | null;

/** The subset of the React 18 API the card relies on. */
export interface ReactLike {
  createElement(type: unknown, props?: Record<string, unknown> | null, ...children: unknown[]): ReactElementLike;
  useState<T>(initial: T | (() => T)): [T, (next: T | ((previous: T) => T)) => void];
  useEffect(effect: () => void | (() => void), deps?: readonly unknown[]): void;
  useCallback<T extends (...args: never[]) => unknown>(callback: T, deps: readonly unknown[]): T;
  useMemo<T>(factory: () => T, deps: readonly unknown[]): T;
  Fragment: unknown;
}

let runtime: ReactLike | undefined;

/**
 * Install the host's React runtime.
 * @param react - value returned by the loader's `require("react")`.
 */
export function setReact(react: ReactLike): void {
  runtime = react;
}

/**
 * The installed runtime.
 * @returns the runtime set by {@link setReact}.
 * @throws when the card is rendered outside the loader (for example if a
 *   host accidentally imports the source module directly).
 */
export function getReact(): ReactLike {
  if (runtime === undefined) {
    throw new Error("dsh-freemodel: the client card needs the host's React runtime");
  }
  return runtime;
}

/** Whether the card can render, without throwing. */
export function hasReact(): boolean {
  return runtime !== undefined;
}
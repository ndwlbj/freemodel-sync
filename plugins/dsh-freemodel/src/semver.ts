/**
 * Just enough semver for the doctor command: compare versions (prereleases
 * included) and test the simple ranges this package declares, such as
 * `>=0.2.1-rc.1 <0.3.0-0` and `^22.19.0 || >=24.0.0`. Not a general parser.
 */

interface Parsed {
  core: [number, number, number];
  pre: string[];
}

function parse(version: string): Parsed | undefined {
  const match = /^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$/.exec(version.trim());
  if (match === null) return undefined;
  return {
    core: [Number(match[1]), Number(match[2]), Number(match[3])],
    pre: match[4] === undefined ? [] : match[4].split("."),
  };
}

function comparePre(a: string[], b: string[]): number {
  if (a.length === 0 || b.length === 0) return b.length - a.length; // release > prerelease
  for (let i = 0; i < Math.max(a.length, b.length); i++) {
    const x = a[i];
    const y = b[i];
    if (x === undefined) return -1;
    if (y === undefined) return 1;
    const nx = /^\d+$/.test(x);
    const ny = /^\d+$/.test(y);
    if (nx && ny) {
      if (Number(x) !== Number(y)) return Number(x) - Number(y);
    } else if (nx !== ny) {
      return nx ? -1 : 1;
    } else if (x !== y) {
      return x < y ? -1 : 1;
    }
  }
  return 0;
}

/**
 * Compare two versions.
 * @returns negative, zero or positive; `undefined` when either is not a version.
 */
export function compareVersions(a: string, b: string): number | undefined {
  const pa = parse(a);
  const pb = parse(b);
  if (pa === undefined || pb === undefined) return undefined;
  for (let i = 0; i < 3; i++) {
    const d = (pa.core[i] as number) - (pb.core[i] as number);
    if (d !== 0) return d;
  }
  return comparePre(pa.pre, pb.pre);
}

function satisfiesComparator(version: string, comparator: string): boolean {
  const caret = /^\^(\d+)\.(\d+)\.(\d+)(-[0-9A-Za-z.-]+)?$/.exec(comparator);
  if (caret !== null) {
    const major = Number(caret[1]);
    const lower = comparator.slice(1);
    const upper = major > 0 ? `${major + 1}.0.0-0` : `0.${Number(caret[2]) + 1}.0-0`;
    return satisfiesComparator(version, `>=${lower}`) && satisfiesComparator(version, `<${upper}`);
  }
  const op = /^(>=|<=|>|<|=)?(.+)$/.exec(comparator);
  if (op === null) return false;
  const cmp = compareVersions(version, op[2] as string);
  if (cmp === undefined) return false;
  switch (op[1]) {
    case ">=":
      return cmp >= 0;
    case "<=":
      return cmp <= 0;
    case ">":
      return cmp > 0;
    case "<":
      return cmp < 0;
    default:
      return cmp === 0;
  }
}

/**
 * Whether a version is inside a range of `||`-joined, space-separated comparators.
 * Prereleases take part, as they do in dsh's own compatibility check.
 */
export function satisfies(version: string, range: string): boolean {
  return range.split("||").some((part) => {
    const comparators = part.trim().split(/\s+/).filter(Boolean);
    return comparators.length > 0 && comparators.every((c) => satisfiesComparator(version, c));
  });
}

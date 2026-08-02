/** 规则树路径与拖拽操作工具 */

export type RuleCondition = {
  operator: string;
  left?: Record<string, unknown>;
  right?: Record<string, unknown>;
  operand?: Record<string, unknown>;
};

export type RuleGroup = {
  all?: Array<RuleCondition | RuleGroup>;
  any?: Array<RuleCondition | RuleGroup>;
  not?: RuleCondition | RuleGroup;
};

export type RuleNode = RuleCondition | RuleGroup;

export function isCondition(node: RuleNode): node is RuleCondition {
  return typeof node === "object" && node !== null && "operator" in node;
}

export function isGroup(node: RuleNode): node is RuleGroup {
  return typeof node === "object" && node !== null && ("all" in node || "any" in node || "not" in node);
}

export function groupMode(group: RuleGroup): "all" | "any" {
  return group.all ? "all" : "any";
}

export function groupItems(group: RuleGroup): RuleNode[] {
  return group.all ?? group.any ?? [];
}

export function setGroupItems(_group: RuleGroup, mode: "all" | "any", items: RuleNode[]): RuleGroup {
  return { [mode]: items };
}

export function cloneNode<T>(node: T): T {
  return JSON.parse(JSON.stringify(node)) as T;
}

/** 获取路径上的父组与索引，path 如 [0, 2] */
export function getAtPath(root: RuleGroup, path: number[]): RuleNode | null {
  if (!path.length) return root;
  let current: RuleNode = root;
  for (const idx of path) {
    if (!isGroup(current)) return null;
    const items = groupItems(current);
    current = items[idx];
    if (current === undefined) return null;
  }
  return current;
}

export function removeAtPath(root: RuleGroup, path: number[]): RuleGroup {
  const next = cloneNode(root);
  if (path.length === 1) {
    const mode = groupMode(next);
    const items = [...groupItems(next)];
    items.splice(path[0], 1);
    return setGroupItems(next, mode, items);
  }
  const parentPath = path.slice(0, -1);
  const parent = getAtPath(next, parentPath);
  if (!parent || !isGroup(parent)) return next;
  const mode = groupMode(parent);
  const items = [...groupItems(parent)];
  items.splice(path[path.length - 1], 1);
  const newParent = setGroupItems(parent, mode, items);
  return replaceAtPath(next, parentPath, newParent);
}

export function replaceAtPath(root: RuleGroup, path: number[], node: RuleNode): RuleGroup {
  const next = cloneNode(root);
  if (!path.length) {
    return node as RuleGroup;
  }
  if (path.length === 1) {
    const mode = groupMode(next);
    const items = [...groupItems(next)];
    items[path[0]] = node;
    return setGroupItems(next, mode, items);
  }
  const parentPath = path.slice(0, -1);
  const parent = getAtPath(next, parentPath);
  if (!parent || !isGroup(parent)) return next;
  const mode = groupMode(parent);
  const items = [...groupItems(parent)];
  items[path[path.length - 1]] = node;
  const newParent = setGroupItems(parent, mode, items);
  return replaceAtPath(next, parentPath, newParent);
}

export function insertAtPath(root: RuleGroup, path: number[], node: RuleNode, index: number): RuleGroup {
  const next = cloneNode(root);
  const target = getAtPath(next, path);
  if (!target || !isGroup(target)) return next;
  const mode = groupMode(target);
  const items = [...groupItems(target)];
  items.splice(index, 0, node);
  return replaceAtPath(next, path, setGroupItems(target, mode, items));
}

export function moveItem(
  root: RuleGroup,
  fromPath: number[],
  toPath: number[],
  toIndex: number,
): RuleGroup {
  const node = getAtPath(root, fromPath);
  if (!node) return root;
  const without = removeAtPath(root, fromPath);
  return insertAtPath(without, toPath, node, toIndex);
}

export function summarizeCondition(cond: RuleCondition): string {
  const op = cond.operator;
  const left = cond.left as { indicator?: string; formula?: string; field?: string } | undefined;
  const right = cond.right as { indicator?: string; formula?: string; constant?: string } | undefined;
  const l =
    left?.formula ?? left?.indicator ?? left?.field ?? "?";
  const r =
    right?.formula ?? right?.indicator ?? right?.constant ?? "?";
  const labels: Record<string, string> = {
    cross_above: "上穿",
    cross_below: "下穿",
    gt: ">",
    lt: "<",
    gte: "≥",
    lte: "≤",
    eq: "=",
  };
  return `${l} ${labels[op] ?? op} ${r}`;
}

export function flattenPaths(group: RuleGroup, prefix: number[] = []): Array<{ path: number[]; node: RuleNode }> {
  const items = groupItems(group);
  const result: Array<{ path: number[]; node: RuleNode }> = [];
  items.forEach((node, idx) => {
    const path = [...prefix, idx];
    result.push({ path, node });
    if (isGroup(node)) {
      result.push(...flattenPaths(node, path));
    }
  });
  return result;
}

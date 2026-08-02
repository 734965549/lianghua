import { useState } from "react";
import { Button, Radio, Tag } from "antd";
import { DeleteOutlined, HolderOutlined, PlusOutlined } from "@ant-design/icons";
import {
  cloneNode,
  flattenPaths,
  groupItems,
  groupMode,
  insertAtPath,
  isCondition,
  isGroup,
  moveItem,
  removeAtPath,
  replaceAtPath,
  setGroupItems,
  summarizeCondition,
  type RuleCondition,
  type RuleGroup,
} from "./ruleTreeUtils";

type Props = {
  value: RuleGroup;
  indicatorIds: string[];
  formulaIds: string[];
  onChange: (group: RuleGroup) => void;
};

function defaultCondition(indicatorIds: string[]): RuleCondition {
  return {
    operator: "cross_above",
    left: { indicator: indicatorIds[0] ?? "fast_ma" },
    right: { indicator: indicatorIds[1] ?? indicatorIds[0] ?? "slow_ma" },
  };
}

export default function RuleCanvas({ value, indicatorIds, formulaIds, onChange }: Props) {
  const [dragPath, setDragPath] = useState<number[] | null>(null);
  const mode = groupMode(value);
  const items = groupItems(value);

  return (
    <div className="rule-canvas">
      <div className="rule-canvas__toolbar">
        <Radio.Group
          size="small"
          value={mode}
          onChange={(e) => onChange(setGroupItems(value, e.target.value, items))}
        >
          <Radio.Button value="all">全部满足 (AND)</Radio.Button>
          <Radio.Button value="any">任一满足 (OR)</Radio.Button>
        </Radio.Group>
        <Button
          size="small"
          icon={<PlusOutlined />}
          onClick={() => onChange(insertAtPath(value, [], defaultCondition(indicatorIds), items.length))}
        >
          添加条件
        </Button>
        <Button
          size="small"
          onClick={() =>
            onChange(
              insertAtPath(value, [], { all: [defaultCondition(indicatorIds)] }, items.length),
            )
          }
        >
          添加规则组
        </Button>
      </div>

      <div
        className="rule-canvas__dropzone"
        onDragOver={(e) => e.preventDefault()}
        onDrop={() => {
          if (dragPath) {
            onChange(moveItem(value, dragPath, [], items.length));
            setDragPath(null);
          }
        }}
      >
        {items.length === 0 ? (
          <div className="rule-canvas__empty">拖拽条件到此处，或点击「添加条件」</div>
        ) : (
          items.map((node, idx) => (
            <NodeView
              key={`${idx}-${isCondition(node) ? node.operator : "g"}`}
              root={value}
              node={node}
              path={[idx]}
              depth={0}
              indicatorIds={indicatorIds}
              dragPath={dragPath}
              onDragStart={setDragPath}
              onChange={onChange}
              onDropTarget={(index) => {
                if (dragPath) {
                  onChange(moveItem(value, dragPath, [], index));
                  setDragPath(null);
                }
              }}
            />
          ))
        )}
      </div>

      <div className="rule-canvas__legend">
        <Tag>条件 {flattenPaths(value).filter((x) => isCondition(x.node)).length} 个</Tag>
        {formulaIds.length > 0 && <Tag color="blue">公式: {formulaIds.join(", ")}</Tag>}
      </div>
    </div>
  );
}

type NodeViewProps = {
  root: RuleGroup;
  node: RuleGroup | RuleCondition;
  path: number[];
  depth: number;
  indicatorIds: string[];
  dragPath: number[] | null;
  onDragStart: (path: number[]) => void;
  onChange: (group: RuleGroup) => void;
  onDropTarget: (index: number) => void;
};

function NodeView({
  root,
  node,
  path,
  depth,
  indicatorIds,
  dragPath,
  onDragStart,
  onChange,
  onDropTarget,
}: NodeViewProps) {
  if (isCondition(node)) {
    const dragging = dragPath !== null && JSON.stringify(dragPath) === JSON.stringify(path);
    return (
      <div
        className={`rule-canvas__node rule-canvas__node--leaf ${dragging ? "rule-canvas__node--dragging" : ""}`}
        style={{ ["--depth" as string]: depth }}
        draggable
        onDragStart={() => onDragStart(path)}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.stopPropagation();
          onDropTarget(path[path.length - 1]);
        }}
      >
        <span className="rule-canvas__connector" aria-hidden />
        <div className="rule-canvas__card">
          <HolderOutlined className="rule-canvas__handle" />
          <span className="rule-canvas__label">{summarizeCondition(node)}</span>
          <Button
            type="link"
            size="small"
            danger
            icon={<DeleteOutlined />}
            onClick={() => onChange(removeAtPath(root, path))}
          />
        </div>
      </div>
    );
  }

  if (!isGroup(node)) return null;
  const subMode = groupMode(node);
  const subItems = groupItems(node);

  return (
    <div
      className="rule-canvas__node rule-canvas__node--group"
      style={{ ["--depth" as string]: depth }}
    >
      <span className="rule-canvas__connector" aria-hidden />
      <div className="rule-canvas__group">
        <div className="rule-canvas__group-header">
          <Tag color={subMode === "all" ? "green" : "orange"}>
            {subMode === "all" ? "全部" : "任一"}
          </Tag>
          <Button
            type="link"
            size="small"
            icon={<PlusOutlined />}
            onClick={() => {
              const updated = insertAtPath(root, path, defaultCondition(indicatorIds), subItems.length);
              onChange(updated);
            }}
          >
            子条件
          </Button>
          <Button
            type="link"
            size="small"
            danger
            onClick={() => onChange(removeAtPath(root, path))}
          >
            删除组
          </Button>
        </div>
        <div className="rule-canvas__children">
          {subItems.map((sub, idx) => (
            <NodeView
              key={idx}
              root={root}
              node={sub}
              path={[...path, idx]}
              depth={depth + 1}
              indicatorIds={indicatorIds}
              dragPath={dragPath}
              onDragStart={onDragStart}
              onChange={onChange}
              onDropTarget={(index) => {
                if (dragPath) {
                  onChange(moveItem(root, dragPath, path, index));
                }
              }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

export { replaceAtPath, cloneNode };

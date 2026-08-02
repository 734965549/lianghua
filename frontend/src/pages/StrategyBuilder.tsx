import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  Radio,
  Steps,
  message,
} from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import PageHeader from "../components/PageHeader";
import BasicInfoStep from "../components/strategy-builder/BasicInfoStep";
import SymbolsStep from "../components/strategy-builder/SymbolsStep";
import IndicatorEditor from "../components/strategy-builder/IndicatorEditor";
import FormulaEditor from "../components/strategy-builder/FormulaEditor";
import RuleGroupEditor from "../components/strategy-builder/RuleGroupEditor";
import RuleCanvas from "../components/strategy-builder/RuleCanvas";
import ExecutionEditor from "../components/strategy-builder/ExecutionEditor";
import RiskEditor from "../components/strategy-builder/RiskEditor";
import StrategySummary from "../components/strategy-builder/StrategySummary";
import AiStrategyPanel from "../components/strategy-builder/AiStrategyPanel";
import type { RuleGroup } from "../components/strategy-builder/ruleTreeUtils";
import {
  DEFAULT_DEFINITION,
  createStrategy,
  getIndicatorCatalog,
  getStrategy,
  getStrategyVersion,
  listStrategyVersions,
  publishStrategy,
  updateStrategy,
  validateStrategyDefinition,
  type StrategyDefinition,
} from "../api/strategies";

const STEPS = [
  { title: "基本信息" },
  { title: "标的范围" },
  { title: "指标" },
  { title: "公式因子" },
  { title: "买入规则" },
  { title: "卖出规则" },
  { title: "执行与风控" },
  { title: "摘要与发布" },
];

export default function StrategyBuilder() {
  const { id } = useParams<{ id: string }>();
  const isEdit = Boolean(id);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [definition, setDefinition] = useState<StrategyDefinition>(DEFAULT_DEFINITION);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const [ruleView, setRuleView] = useState<"form" | "canvas">("canvas");

  const catalog = useQuery({
    queryKey: ["indicator-catalog"],
    queryFn: getIndicatorCatalog,
  });

  const existing = useQuery({
    queryKey: ["strategy", id],
    queryFn: () => getStrategy(id!),
    enabled: isEdit,
  });

  useEffect(() => {
    if (!existing.data) return;
    setName(existing.data.name);
    setDescription(existing.data.description);
    const loadDefinition = async () => {
      try {
        const versions = await listStrategyVersions(existing.data!.strategy_id);
        const draft = versions.find((v) => v.status === "draft");
        if (draft) {
          const ver = await getStrategyVersion(existing.data!.strategy_id, draft.version);
          setDefinition(ver.definition);
          return;
        }
        if (existing.data!.current_version) {
          const ver = await getStrategyVersion(
            existing.data!.strategy_id,
            existing.data!.current_version,
          );
          setDefinition(ver.definition);
        }
      } catch {
        /* 忽略 */
      }
    };
    void loadDefinition();
  }, [existing.data]);

  const indicatorIds = useMemo(
    () => (definition.indicators ?? []).map((i) => String(i.id)),
    [definition.indicators],
  );

  const formulaIds = useMemo(
    () => (definition.formulas ?? []).map((f) => String(f.id)),
    [definition.formulas],
  );

  const indicatorOutputs = useMemo(() => {
    const map: Record<string, string[]> = {};
    const catalogItems = catalog.data?.indicators ?? [];
    for (const ind of definition.indicators ?? []) {
      const meta = catalogItems.find((c) => c.type === ind.type);
      map[String(ind.id)] = meta?.outputs ?? ["value"];
    }
    return map;
  }, [definition.indicators, catalog.data?.indicators]);

  const saveDraft = useMutation({
    mutationFn: async () => {
      if (isEdit && id) {
        return updateStrategy(id, { name, description, definition });
      }
      return createStrategy({ name, description, definition });
    },
    onSuccess: (data) => {
      message.success("草稿已保存");
      void qc.invalidateQueries({ queryKey: ["strategies"] });
      if (!isEdit) {
        navigate(`/strategies/${data.strategy_id}/edit`, { replace: true });
      }
    },
  });

  const validate = useMutation({
    mutationFn: async () => {
      if (!isEdit || !id) {
        message.info("请先保存草稿后再校验");
        return { valid: false, errors: ["请先保存草稿"] };
      }
      return validateStrategyDefinition(id, definition);
    },
    onSuccess: (result) => {
      if (!result) return;
      setValidationErrors(result.errors);
      if (result.valid) message.success("校验通过");
      else message.error("校验失败");
    },
  });

  const publish = useMutation({
    mutationFn: async () => {
      let strategyId = id;
      if (!strategyId) {
        const created = await createStrategy({ name, description, definition });
        strategyId = created.strategy_id;
      } else {
        await updateStrategy(strategyId, { name, description, definition });
      }
      return publishStrategy(strategyId!);
    },
    onSuccess: () => {
      message.success("策略已发布");
      void qc.invalidateQueries({ queryKey: ["strategies"] });
      navigate("/strategies");
    },
  });

  const renderRuleEditor = (
    ruleKey: "entry_rule" | "exit_rule",
    defaultGroup: RuleGroup,
  ) => (
    <div>
      <Radio.Group
        size="small"
        value={ruleView}
        onChange={(e) => setRuleView(e.target.value)}
        style={{ marginBottom: 12 }}
      >
        <Radio.Button value="canvas">可视化拖拽</Radio.Button>
        <Radio.Button value="form">表单编辑</Radio.Button>
      </Radio.Group>
      {ruleView === "canvas" ? (
        <RuleCanvas
          value={(definition[ruleKey] as RuleGroup) ?? defaultGroup}
          indicatorIds={indicatorIds}
          formulaIds={formulaIds}
          onChange={(group) => setDefinition({ ...definition, [ruleKey]: group })}
        />
      ) : (
        <RuleGroupEditor
          value={(definition[ruleKey] as RuleGroup) ?? defaultGroup}
          indicatorIds={indicatorIds}
          formulaIds={formulaIds}
          indicatorOutputs={indicatorOutputs}
          operators={catalog.data?.operators}
          onChange={(group) => setDefinition({ ...definition, [ruleKey]: group })}
        />
      )}
    </div>
  );

  return (
    <div>
      <PageHeader
        eyebrow="STRATEGY BUILDER"
        title={isEdit ? "编辑策略" : "新建策略"}
        description="支持多标的、公式因子与可视化拖拽规则编辑。"
      />

      <Card size="small" style={{ marginBottom: 16 }}>
        <Steps current={step} size="small" items={STEPS} onChange={setStep} />
      </Card>

      <Card size="small" title={STEPS[step].title}>
        {step === 0 && (
          <div className="research-form-grid">
            <div className="span-2">
              <AiStrategyPanel
                onGenerated={({ name: aiName, description: aiDesc, definition: aiDef }) => {
                  if (aiName) setName(aiName);
                  if (aiDesc) setDescription(aiDesc);
                  setDefinition(aiDef);
                  setValidationErrors([]);
                }}
              />
            </div>
            <Form.Item label="策略名称" required className="span-2">
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="如：多标的均线策略" />
            </Form.Item>
            <Form.Item label="描述" className="span-2">
              <Input.TextArea rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
            </Form.Item>
            <div className="span-2">
              <BasicInfoStep definition={definition} onChange={setDefinition} />
            </div>
          </div>
        )}

        {step === 1 && <SymbolsStep definition={definition} onChange={setDefinition} />}

        {step === 2 && (
          <IndicatorEditor
            definition={definition}
            catalog={catalog.data?.indicators}
            onChange={setDefinition}
          />
        )}

        {step === 3 && (
          <FormulaEditor
            definition={definition}
            indicatorIds={indicatorIds}
            indicatorOutputs={indicatorOutputs}
            helpText={catalog.data?.formula_ref_help}
            onChange={setDefinition}
          />
        )}

        {step === 4 && renderRuleEditor("entry_rule", { all: [] })}
        {step === 5 && renderRuleEditor("exit_rule", { any: [] })}

        {step === 6 && (
          <div style={{ display: "grid", gap: 16 }}>
            <ExecutionEditor definition={definition} onChange={setDefinition} />
            <RiskEditor definition={definition} onChange={setDefinition} />
          </div>
        )}

        {step === 7 && (
          <StrategySummary name={name} definition={definition} validationErrors={validationErrors} />
        )}

        {validationErrors.length > 0 && step !== 7 && (
          <Alert
            type="warning"
            showIcon
            style={{ marginTop: 12 }}
            message={`${validationErrors.length} 个校验问题`}
            description={validationErrors.slice(0, 3).join("；")}
          />
        )}

        <div style={{ display: "flex", gap: 8, marginTop: 16, justifyContent: "space-between" }}>
          <div>
            <Button disabled={step === 0} onClick={() => setStep((s) => s - 1)}>
              上一步
            </Button>
            <Button
              style={{ marginLeft: 8 }}
              disabled={step >= STEPS.length - 1}
              onClick={() => setStep((s) => s + 1)}
            >
              下一步
            </Button>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <Button onClick={() => validate.mutate()} loading={validate.isPending}>
              校验
            </Button>
            <Button onClick={() => saveDraft.mutate()} loading={saveDraft.isPending}>
              保存草稿
            </Button>
            <Button type="primary" onClick={() => publish.mutate()} loading={publish.isPending}>
              发布
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
}

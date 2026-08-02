import { useState } from "react";
import {
  Button,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import { PlusOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { Instrument, InstrumentCatalog } from "../api/types";

type WatchlistItem = {
  id: string;
  symbol: string;
  market: string;
  alias: string;
  enabled: boolean;
  download_1d: boolean;
  download_1m: boolean;
  created_at: string;
  updated_at: string;
};

export default function Watchlist() {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [form] = Form.useForm();
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["watchlist"],
    queryFn: () => api.get<WatchlistItem[]>("/watchlist"),
  });

  const { data: instrumentCatalog, isLoading: instrumentsLoading } = useQuery({
    queryKey: ["instruments", search],
    queryFn: () =>
      api.get<InstrumentCatalog>(
        `/instruments?query=${encodeURIComponent(search)}&limit=50`,
      ),
    enabled: open,
  });

  const addMut = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post("/watchlist", body),
    onSuccess: () => {
      message.success("已添加");
      qc.invalidateQueries({ queryKey: ["watchlist"] });
      setOpen(false);
      form.resetFields();
      setSearch("");
    },
  });

  const patchMut = useMutation({
    mutationFn: ({ market, symbol, body }: { market: string; symbol: string; body: Record<string, unknown> }) =>
      api.patch(`/watchlist/${market}/${symbol}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlist"] }),
  });

  const delMut = useMutation({
    mutationFn: ({ market, symbol }: { market: string; symbol: string }) =>
      api.del(`/watchlist/${market}/${symbol}`),
    onSuccess: () => {
      message.success("已删除");
      qc.invalidateQueries({ queryKey: ["watchlist"] });
    },
  });

  const instrumentOptions = instrumentCatalog?.items.map((item) => ({
    value: `${item.market}:${item.symbol}`,
    label: `${item.symbol} - ${item.name}`,
    instrument: item,
  })) ?? [];

  const handleInstrumentSelect = (_value: string, option: { instrument: Instrument }) => {
    const item = option.instrument;
    form.setFieldsValue({
      symbol: item.symbol,
      market: item.market,
      alias: item.name,
    });
  };

  return (
    <div>
      <Typography.Title level={3} style={{ marginTop: 0 }}>
        自选标的管理
      </Typography.Title>
      <Typography.Paragraph type="secondary">
        配置关注的标的，启用后将自动订阅实时行情并参与定时数据下载。
      </Typography.Paragraph>

      <Space style={{ marginBottom: 16 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>
          添加标的
        </Button>
      </Space>

      <Table
        rowKey="id"
        loading={isLoading}
        dataSource={data ?? []}
        pagination={false}
        columns={[
          { title: "代码", dataIndex: "symbol" },
          {
            title: "市场",
            dataIndex: "market",
            render: (v: string) => <Tag>{v}</Tag>,
          },
          { title: "别名", dataIndex: "alias" },
          {
            title: "启用",
            dataIndex: "enabled",
            render: (v: boolean, r: WatchlistItem) => (
              <Switch
                aria-label={`${r.symbol} 是否启用实时订阅`}
                checked={v}
                onChange={(checked) =>
                  patchMut.mutate({ market: r.market, symbol: r.symbol, body: { enabled: checked } })
                }
              />
            ),
          },
          {
            title: "下载日线",
            dataIndex: "download_1d",
            render: (v: boolean, r: WatchlistItem) => (
              <Switch
                aria-label={`${r.symbol} 是否下载日线`}
                checked={v}
                onChange={(checked) =>
                  patchMut.mutate({ market: r.market, symbol: r.symbol, body: { download_1d: checked } })
                }
              />
            ),
          },
          {
            title: "下载分钟",
            dataIndex: "download_1m",
            render: (v: boolean, r: WatchlistItem) => (
              <Switch
                aria-label={`${r.symbol} 是否下载分钟线`}
                checked={v}
                onChange={(checked) =>
                  patchMut.mutate({ market: r.market, symbol: r.symbol, body: { download_1m: checked } })
                }
              />
            ),
          },
          {
            title: "操作",
            render: (_: unknown, r: WatchlistItem) => (
              <Button
                danger
                size="small"
                onClick={() => delMut.mutate({ market: r.market, symbol: r.symbol })}
              >
                删除
              </Button>
            ),
          },
        ]}
      />

      <Modal
        title="添加标的"
        open={open}
        onCancel={() => {
          setOpen(false);
          setSearch("");
          form.resetFields();
        }}
        onOk={() => form.submit()}
        confirmLoading={addMut.isPending}
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={{ enabled: true, download_1d: true, download_1m: false }}
          onFinish={({ instrument_key: _instrumentKey, ...values }) => addMut.mutate(values)}
        >
          <Form.Item
            name="instrument_key"
            label="选择标的"
            rules={[{ required: true, message: "请选择标的" }]}
          >
            <Select
              aria-label="选择要添加的标的"
              showSearch
              placeholder="输入代码或名称搜索，如 贵州茅台、600519"
              loading={instrumentsLoading}
              filterOption={false}
              options={instrumentOptions}
              onSearch={setSearch}
              onSelect={handleInstrumentSelect}
              notFoundContent={instrumentsLoading ? "加载中..." : "无匹配标的"}
            />
          </Form.Item>
          <Form.Item name="symbol" hidden>
            <Input />
          </Form.Item>
          <Form.Item name="market" hidden>
            <Input />
          </Form.Item>
          <Form.Item name="alias" label="别名">
            <Input placeholder="可选别名" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

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
  const [form] = Form.useForm();
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["watchlist"],
    queryFn: () => api.get<WatchlistItem[]>("/watchlist"),
  });

  const addMut = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post("/watchlist", body),
    onSuccess: () => {
      message.success("已添加");
      qc.invalidateQueries({ queryKey: ["watchlist"] });
      setOpen(false);
      form.resetFields();
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

  return (
    <div>
      <Typography.Title level={3} style={{ marginTop: 0 }}>
        股票池管理
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
        onCancel={() => setOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={addMut.isPending}
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={{ market: "stock", enabled: true, download_1d: true, download_1m: false }}
          onFinish={(values) => addMut.mutate(values)}
        >
          <Form.Item name="symbol" label="代码" rules={[{ required: true }]}>
            <Input placeholder="600000.SH 或 IF2509" />
          </Form.Item>
          <Form.Item name="market" label="市场" rules={[{ required: true }]}>
            <Select
              options={[
                { value: "stock", label: "股票" },
                { value: "futures", label: "期货" },
              ]}
            />
          </Form.Item>
          <Form.Item name="alias" label="别名">
            <Input placeholder="可选" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

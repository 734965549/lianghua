import { useState } from "react";
import { Button, message } from "antd";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import ConfirmDialog from "./ConfirmDialog";

type Props = {
  /** 按钮尺寸，顶部栏可用 small */
  size?: "small" | "middle" | "large";
};

/**
 * 一键停止：二次确认并填写原因后调用 /risk/emergency-stop。
 * 文档要求仪表盘、自动交易页必须可见。
 */
export default function EmergencyStopButton({ size = "middle" }: Props) {
  const [open, setOpen] = useState(false);
  const qc = useQueryClient();

  const emergency = useMutation({
    mutationFn: (reason: string) =>
      api.post<{ status: string; cancelled_orders: number }>("/risk/emergency-stop", {
        reason,
        cancel_open_orders: true,
      }),
    onSuccess: (res) => {
      message.warning(`已进入紧急停止（撤单 ${res?.cancelled_orders ?? 0} 笔）`);
      qc.invalidateQueries({ queryKey: ["risk-status"] });
      qc.invalidateQueries({ queryKey: ["system-status"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      qc.invalidateQueries({ queryKey: ["health"] });
    },
  });

  return (
    <>
      <Button danger type="primary" size={size} onClick={() => setOpen(true)}>
        一键停止
      </Button>
      <ConfirmDialog
        open={open}
        title="确认一键停止？"
        impact="将立即禁止所有新委托，并默认撤销未成交委托。"
        okText="立即停止"
        danger
        confirmLoading={emergency.isPending}
        onCancel={() => setOpen(false)}
        onConfirm={async (reason) => {
          await emergency.mutateAsync(reason);
          setOpen(false);
        }}
      />
    </>
  );
}

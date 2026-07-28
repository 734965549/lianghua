import { Input, Modal } from "antd";
import { useEffect, useState, type ReactNode } from "react";

export type ConfirmDialogProps = {
  open: boolean;
  title: string;
  /** 影响范围说明（文档要求必须展示） */
  impact: ReactNode;
  okText?: string;
  cancelText?: string;
  danger?: boolean;
  confirmLoading?: boolean;
  reasonPlaceholder?: string;
  onCancel: () => void;
  onConfirm: (reason: string) => void | Promise<void>;
};

/**
 * 危险操作二次确认：必须输入原因，确认后由调用方写入审计。
 */
export default function ConfirmDialog({
  open,
  title,
  impact,
  okText = "确认",
  cancelText = "取消",
  danger = false,
  confirmLoading = false,
  reasonPlaceholder = "必填，将写入审计日志",
  onCancel,
  onConfirm,
}: ConfirmDialogProps) {
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open) setReason("");
  }, [open]);

  const trimmed = reason.trim();

  const handleOk = async () => {
    if (!trimmed) return;
    setSubmitting(true);
    try {
      await onConfirm(trimmed);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open={open}
      title={title}
      okText={okText}
      cancelText={cancelText}
      okButtonProps={{ danger, disabled: !trimmed }}
      confirmLoading={confirmLoading || submitting}
      onCancel={onCancel}
      onOk={handleOk}
      destroyOnClose
      maskClosable={false}
    >
      <div style={{ marginBottom: 12 }}>{impact}</div>
      <div style={{ marginBottom: 6, fontWeight: 500 }}>操作原因（必填）</div>
      <Input.TextArea
        rows={3}
        value={reason}
        placeholder={reasonPlaceholder}
        onChange={(e) => setReason(e.target.value)}
        autoFocus
      />
    </Modal>
  );
}

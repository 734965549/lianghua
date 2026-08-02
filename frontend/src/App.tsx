import { useEffect } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ConfigProvider, App as AntdApp, theme as antdTheme } from "antd";
import zhCN from "antd/locale/zh_CN";
import { RouterProvider } from "react-router-dom";
import { router } from "./router";
import { ws } from "./api/ws";

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1 } },
});

export default function App() {
  useEffect(() => {
    void ws.connect();
    return () => ws.disconnect();
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <ConfigProvider
        locale={zhCN}
        theme={{
          algorithm: antdTheme.darkAlgorithm,
          token: {
            colorPrimary: "#ff4d57",
            colorInfo: "#37b7ff",
            colorSuccess: "#18c78c",
            colorWarning: "#ffb547",
            colorError: "#ff4d57",
            colorBgBase: "#080c12",
            colorBgContainer: "#111923",
            colorBgElevated: "#17212e",
            colorBorder: "#263342",
            colorBorderSecondary: "#1d2937",
            colorText: "#e7edf5",
            colorTextSecondary: "#8d9bad",
            borderRadius: 4,
            borderRadiusLG: 6,
            fontFamily:
              '"Inter", "Segoe UI Variable", "PingFang SC", "Microsoft YaHei", sans-serif',
            controlHeight: 32,
          },
          components: {
            Layout: {
              bodyBg: "#080c12",
              headerBg: "#0b1119",
              siderBg: "#0b1119",
            },
            Menu: {
              darkItemBg: "#0b1119",
              darkSubMenuItemBg: "#0b1119",
              darkItemSelectedBg: "#2a151a",
              darkItemSelectedColor: "#ff6570",
              itemBorderRadius: 3,
              itemHeight: 38,
            },
            Card: {
              headerBg: "#111923",
            },
            Table: {
              headerBg: "#0e151e",
              headerColor: "#8391a3",
              rowHoverBg: "#182331",
              borderColor: "#202c3a",
              cellPaddingBlockSM: 8,
              cellPaddingInlineSM: 10,
            },
            Button: {
              primaryShadow: "none",
              dangerShadow: "none",
            },
            Statistic: {
              contentFontSize: 24,
              titleFontSize: 12,
            },
          },
        }}
      >
        <AntdApp>
          <RouterProvider router={router} />
        </AntdApp>
      </ConfigProvider>
    </QueryClientProvider>
  );
}

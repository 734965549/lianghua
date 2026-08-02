import { lazy, Suspense } from "react";
import { createBrowserRouter, Navigate } from "react-router-dom";
import { Spin } from "antd";
import MainLayout from "./layouts/MainLayout";

const Dashboard = lazy(() => import("./pages/Dashboard"));
const Market = lazy(() => import("./pages/Market"));
const Strategies = lazy(() => import("./pages/Strategies"));
const StrategyBuilder = lazy(() => import("./pages/StrategyBuilder"));
const Trading = lazy(() => import("./pages/Trading"));
const Positions = lazy(() => import("./pages/Positions"));
const History = lazy(() => import("./pages/History"));
const AiReports = lazy(() => import("./pages/AiReports"));
const RiskSettings = lazy(() => import("./pages/RiskSettings"));
const Settings = lazy(() => import("./pages/Settings"));
const Logs = lazy(() => import("./pages/Logs"));
const Watchlist = lazy(() => import("./pages/Watchlist"));
const DataManagement = lazy(() => import("./pages/DataManagement"));
const Backtest = lazy(() => import("./pages/Backtest"));
const NotFound = lazy(() => import("./pages/NotFound"));

function LazyPage({ children }: { children: React.ReactNode }) {
  return (
    <Suspense
      fallback={
        <div style={{ padding: 48, textAlign: "center" }}>
          <Spin description="加载中…" />
        </div>
      }
    >
      {children}
    </Suspense>
  );
}

export const router = createBrowserRouter([
  {
    path: "/",
    element: <MainLayout />,
    children: [
      { index: true, element: <Navigate to="/dashboard" replace /> },
      { path: "dashboard", element: <LazyPage><Dashboard /></LazyPage> },
      { path: "market", element: <LazyPage><Market /></LazyPage> },
      { path: "watchlist", element: <LazyPage><Watchlist /></LazyPage> },
      { path: "data", element: <LazyPage><DataManagement /></LazyPage> },
      { path: "strategies", element: <LazyPage><Strategies /></LazyPage> },
      { path: "strategies/new", element: <LazyPage><StrategyBuilder /></LazyPage> },
      { path: "strategies/:id/edit", element: <LazyPage><StrategyBuilder /></LazyPage> },
      { path: "backtest", element: <LazyPage><Backtest /></LazyPage> },
      { path: "trading", element: <LazyPage><Trading /></LazyPage> },
      { path: "positions", element: <LazyPage><Positions /></LazyPage> },
      { path: "history", element: <LazyPage><History /></LazyPage> },
      { path: "ai-reports", element: <LazyPage><AiReports /></LazyPage> },
      { path: "risk-settings", element: <LazyPage><RiskSettings /></LazyPage> },
      { path: "settings", element: <LazyPage><Settings /></LazyPage> },
      { path: "logs", element: <LazyPage><Logs /></LazyPage> },
      { path: "*", element: <LazyPage><NotFound /></LazyPage> },
    ],
  },
]);

import { useSystemStatus } from "../hooks/useSystemStatus";
import { SYSTEM_STATUS_LABEL } from "../utils/status";

export default function SystemStatusBar() {
  const { status, dbOk, stockSdk, futuresSdk } = useSystemStatus();
  const safe = status === "trading" || status === "ready";

  return (
    <div className="system-status-bar">
      <span className={`system-state system-state--${safe ? "safe" : "danger"}`}>
        <i />
        {SYSTEM_STATUS_LABEL[status] ?? status}
      </span>
      <span className={dbOk ? "connection-ok" : "connection-bad"}>
        DB {dbOk ? "ON" : "OFF"}
      </span>
      <span className={stockSdk === "connected" ? "connection-ok" : "connection-bad"}>
        S {stockSdk === "connected" ? "ON" : "OFF"}
      </span>
      <span className={futuresSdk === "connected" ? "connection-ok" : "connection-bad"}>
        F {futuresSdk === "connected" ? "ON" : "OFF"}
      </span>
    </div>
  );
}

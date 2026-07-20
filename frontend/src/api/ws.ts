type EventTopic =
  | "system.status"
  | "quote.update"
  | "strategy.signal"
  | "order.update"
  | "trade.update"
  | "risk.event"
  | "audit.event";

type Handler = (data: unknown) => void;

class WsClient {
  private ws: WebSocket | null = null;
  private handlers: Record<EventTopic, Handler[]> = {
    "system.status": [],
    "quote.update": [],
    "strategy.signal": [],
    "order.update": [],
    "trade.update": [],
    "risk.event": [],
    "audit.event": [],
  };
  private reconnectTimer: number | null = null;
  private shouldReconnect = true;

  connect() {
    this.shouldReconnect = true;
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const host = window.location.host;
    this.ws = new WebSocket(`${proto}://${host}/api/ws/events`);
    this.ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data) as { topic: EventTopic; data: unknown };
        this.handlers[msg.topic]?.forEach((h) => h(msg.data));
      } catch {
        // ignore malformed
      }
    };
    this.ws.onclose = () => {
      if (!this.shouldReconnect) return;
      this.reconnectTimer = window.setTimeout(() => this.connect(), 5000);
    };
  }

  on(topic: EventTopic, handler: Handler) {
    this.handlers[topic].push(handler);
    return () => {
      this.handlers[topic] = this.handlers[topic].filter((h) => h !== handler);
    };
  }

  disconnect() {
    this.shouldReconnect = false;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.ws?.close();
    this.ws = null;
  }
}

export const ws = new WsClient();

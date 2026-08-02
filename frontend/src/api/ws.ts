export type EventTopic =
  | "system.status"
  | "quote.update"
  | "strategy.signal"
  | "order.update"
  | "trade.update"
  | "risk.event"
  | "audit.event"
  | "data.download.progress";

type Handler = (data: unknown) => void;

interface WsMessage {
  topic?: EventTopic;
  data?: unknown;
  event_time?: string;
  correlation_id?: string;
  error?: string;
  subscribed?: string[];
  unsubscribed?: string[];
}

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
    "data.download.progress": [],
  };
  private reconnectTimer: number | null = null;
  private shouldReconnect = true;
  private token = "";
  private pendingTopics: EventTopic[] = [];

  async fetchToken(): Promise<string> {
    try {
      const res = await fetch("/api/system/status");
      const body = await res.json();
      return body.success ? (body.data?.ws_token ?? "") : "";
    } catch {
      return "";
    }
  }

  async connect() {
    this.shouldReconnect = true;
    this.token = await this.fetchToken();

    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const host = window.location.host;
    const qs = this.token ? `?token=${encodeURIComponent(this.token)}` : "";
    this.ws = new WebSocket(`${proto}://${host}/api/ws/events${qs}`);

    this.ws.onopen = () => {
      // 重新连接后，自动恢复之前的主题订阅
      if (this.pendingTopics.length > 0) {
        this.subscribe(this.pendingTopics);
      }
    };

    this.ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data) as WsMessage;
        if (msg.error || !msg.topic) {
          return;
        }
        const topic = msg.topic;
        this.handlers[topic]?.forEach((h: Handler) => h(msg.data));
      } catch {
        // ignore malformed
      }
    };

    this.ws.onclose = () => {
      if (!this.shouldReconnect) return;
      this.reconnectTimer = window.setTimeout(() => this.connect(), 5000);
    };
  }

  private send(msg: unknown) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    }
  }

  subscribe(topics: EventTopic[]) {
    const unique = [...new Set(topics)];
    for (const t of unique) {
      if (!this.pendingTopics.includes(t)) {
        this.pendingTopics.push(t);
      }
    }
    this.send({ action: "subscribe", topics: unique });
  }

  unsubscribe(topics: EventTopic[]) {
    this.pendingTopics = this.pendingTopics.filter((t) => !topics.includes(t));
    this.send({ action: "unsubscribe", topics });
  }

  on(topic: EventTopic, handler: Handler) {
    this.handlers[topic].push(handler);
    this.subscribe([topic]);
    return () => {
      this.handlers[topic] = this.handlers[topic].filter((h) => h !== handler);
      if (this.handlers[topic].length === 0) {
        this.unsubscribe([topic]);
      }
    };
  }

  disconnect() {
    this.shouldReconnect = false;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.ws?.close();
    this.ws = null;
    this.pendingTopics = [];
  }
}

export const ws = new WsClient();

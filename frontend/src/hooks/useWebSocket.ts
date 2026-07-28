import { useEffect, useRef } from "react";
import { ws, type EventTopic } from "../api/ws";

/**
 * 订阅 WebSocket 主题；handler 通过 ref 保持最新，避免重复订阅。
 */
export function useWebSocket(topic: EventTopic, handler: (data: unknown) => void) {
  const handlerRef = useRef(handler);
  handlerRef.current = handler;

  useEffect(() => {
    return ws.on(topic, (data) => handlerRef.current(data));
  }, [topic]);
}

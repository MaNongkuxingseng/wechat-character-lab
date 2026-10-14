import { useCallback, useEffect, useRef, useState } from "react";
import { createSession, getEventsUrl, getHealth, getRoles } from "../api/client";
import type { RoleProfile, ServerEvent, SessionRead } from "../types";

type ConnectionState = "checking" | "connected" | "disconnected";

export function useSession() {
  const [roles, setRoles] = useState<RoleProfile[]>([]);
  const [session, setSession] = useState<SessionRead | null>(null);
  const [connection, setConnection] = useState<ConnectionState>("checking");
  const [events, setEvents] = useState<ServerEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let active = true;
    Promise.all([getHealth(), getRoles()])
      .then(([, loadedRoles]) => {
        if (active) {
          setRoles(loadedRoles);
          setConnection("connected");
        }
      })
      .catch(() => {
        if (active) {
          setConnection("disconnected");
          setError("无法连接本机后端。请启动 FastAPI 服务并完成数据库迁移。");
        }
      });
    return () => {
      active = false;
      socketRef.current?.close();
    };
  }, []);

  const startSession = useCallback(async (topic: string) => {
    setError(null);
    try {
      const created = await createSession(topic);
      setSession(created);
      setEvents([]);
      socketRef.current?.close();
      const socket = new WebSocket(getEventsUrl(created.id));
      socketRef.current = socket;
      socket.onmessage = (message: MessageEvent<string>) => {
        try {
          const event = JSON.parse(message.data) as ServerEvent;
          setEvents((current) => [...current, event]);
          if (event.type === "session.state") {
            setSession((current) => current ? { ...current, status: event.status } : current);
          }
        } catch {
          setError("收到无法识别的服务端事件。");
        }
      };
      socket.onopen = () => {
        socket.send(JSON.stringify({ type: "session.start", client_message_id: `start-${created.id}` }));
      };
      socket.onerror = () => setError("会话事件连接失败。");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "创建会话失败。");
    }
  }, []);

  const sendMessage = useCallback((text: string) => {
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN || !text.trim()) return false;
    socket.send(JSON.stringify({
      type: "user.message",
      client_message_id: crypto.randomUUID(),
      text: text.trim(),
    }));
    return true;
  }, []);

  const stopSession = useCallback(() => {
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) return false;
    socket.send(JSON.stringify({ type: "session.stop", client_message_id: crypto.randomUUID() }));
    return true;
  }, []);

  return { roles, session, connection, events, error, startSession, sendMessage, stopSession };
}

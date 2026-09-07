import { useCallback, useEffect, useState } from "react";
import styles from "./App.module.scss";

/** Ответ проверочного эндпоинта. */
interface PingResponse {
  status: string;
  frozen: string;
}

/**
 * Проверка связки, а не приложение.
 *
 * Три вещи, которые нужно подтвердить: HTTP-запрос доходит до Python,
 * WebSocket держит поток событий с частотой уровня микрофона, и всё это
 * работает внутри собранного .exe так же, как из исходников.
 */
export function App() {
  const [ping, setPing] = useState<PingResponse | null>(null);
  const [pingError, setPingError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [tick, setTick] = useState(0);
  const [wsState, setWsState] = useState<"connecting" | "open" | "closed">("connecting");

  const callPing = useCallback(async () => {
    setPingError(null);
    setPing(null);
    setPending(true);
    try {
      const response = await fetch("/api/ping");
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      setPing((await response.json()) as PingResponse);
    } catch (error) {
      setPingError(error instanceof Error ? error.message : String(error));
    } finally {
      setPending(false);
    }
  }, []);

  useEffect(() => {
    // Адрес берём из текущей страницы: порт случайный и заранее неизвестен
    const url = `ws://${window.location.host}/ws`;
    const socket = new WebSocket(url);

    socket.onopen = () => setWsState("open");
    socket.onclose = () => setWsState("closed");
    socket.onmessage = (event) => {
      const message = JSON.parse(event.data as string) as { type: string; value: number };
      if (message.type === "tick") setTick(message.value);
    };

    return () => socket.close();
  }, []);

  return (
    <main className={styles.root}>
      <h1 className={styles.title}>VoxDuo</h1>
      <p className={styles.subtitle}>Проверка связки React + FastAPI + pywebview</p>

      <section className={styles.card}>
        <h2>HTTP</h2>
        <button
          type="button"
          className={styles.button}
          onClick={callPing}
          disabled={pending}
        >
          {pending ? "Запрашиваю…" : "Позвать /api/ping"}
        </button>
        {ping && (
          <p className={styles.ok} key={ping.status}>
            Ответ: {ping.status} · собранное приложение: {ping.frozen}
          </p>
        )}
        {pingError && <p className={styles.error}>Ошибка: {pingError}</p>}
      </section>

      <section className={styles.card}>
        <h2>WebSocket</h2>
        <p className={styles.state} data-state={wsState}>
          Соединение: {wsState}
        </p>
        <p className={styles.counter}>{tick}</p>
        <p className={styles.hint}>
          Счётчик идёт пятнадцать раз в секунду — с той же частотой пойдёт уровень микрофона
        </p>
      </section>
    </main>
  );
}

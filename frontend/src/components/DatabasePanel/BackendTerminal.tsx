import { useEffect, useRef, useState } from 'react';
import './BackendTerminal.css';

interface LogLine {
  id: number;
  timestamp: string;
  level: string;
  logger: string;
  message: string;
}

let _lineId = 0;

const LEVEL_CLASS: Record<string, string> = {
  DEBUG: 'level-debug',
  INFO: 'level-info',
  WARNING: 'level-warning',
  ERROR: 'level-error',
  CRITICAL: 'level-error',
  PRINT: 'level-print',
  HISTORY: 'level-history',
};

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return '';
  }
}

export default function BackendTerminal() {
  const [lines, setLines] = useState<LogLine[]>([]);
  const [autoScroll, setAutoScroll] = useState(true);
  const outputRef = useRef<HTMLDivElement>(null);
  const autoScrollRef = useRef(true);

  // Keep ref in sync with state so the scroll handler can read it without stale closure
  useEffect(() => {
    autoScrollRef.current = autoScroll;
  }, [autoScroll]);

  // SSE connection
  useEffect(() => {
    const es = new EventSource('http://localhost:8000/api/v1/logs/stream');

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'ping') return;
        const line: LogLine = {
          id: ++_lineId,
          timestamp: data.timestamp ?? '',
          level: (data.level ?? 'INFO').toUpperCase(),
          logger: data.logger ?? '',
          message: data.message ?? '',
        };
        setLines((prev) => {
          const next = [...prev, line];
          // Cap at 1000 lines
          return next.length > 1000 ? next.slice(next.length - 1000) : next;
        });
      } catch {
        // ignore parse errors
      }
    };

    es.onerror = () => {
      // EventSource will auto-reconnect; nothing to do
    };

    return () => es.close();
  }, []);

  // Auto-scroll to bottom when new lines arrive
  useEffect(() => {
    if (autoScrollRef.current && outputRef.current) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }
  }, [lines]);

  function handleScroll() {
    const el = outputRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 32;
    if (atBottom !== autoScrollRef.current) {
      setAutoScroll(atBottom);
    }
  }

  return (
    <div className="terminal-container">
      <div className="terminal-toolbar">
        <label className="terminal-autoscroll">
          <input
            type="checkbox"
            checked={autoScroll}
            onChange={(e) => setAutoScroll(e.target.checked)}
          />
          Auto-scroll
        </label>
        <button className="terminal-clear-btn" onClick={() => setLines([])}>
          Clear
        </button>
        <span className="terminal-count">{lines.length} lines</span>
      </div>

      <div
        className="terminal-output"
        ref={outputRef}
        onScroll={handleScroll}
      >
        {lines.length === 0 && (
          <div className="terminal-empty">Waiting for backend logs…</div>
        )}
        {lines.map((line) => (
          <div key={line.id} className="terminal-line">
            <span className="terminal-ts">{formatTime(line.timestamp)}</span>
            <span className={`terminal-level ${LEVEL_CLASS[line.level] ?? 'level-info'}`}>
              {line.level}
            </span>
            <span className="terminal-logger">{line.logger}</span>
            <span className="terminal-msg">{line.message}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

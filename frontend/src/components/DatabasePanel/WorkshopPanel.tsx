import { useState, useEffect, useRef } from 'react';
import { conversationAPI } from '../../api/conversationAPI';
import './WorkshopPanel.css';

interface WorkshopPanelProps {
  agentId: string;
  conversationId?: string;
  onConversationChange?: (conversationId: string) => void;
}

interface ToolEvent {
  id: string;
  type: 'tool_call' | 'tool_result';
  name?: string;
  arguments?: Record<string, unknown>;
  result?: unknown;
  error?: string;
  timestamp: string;
}

interface ToolCallGroup {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
  result?: unknown;
  error?: string;
  timestamp: string;
  pending: boolean;
}

export default function WorkshopPanel({ agentId, conversationId, onConversationChange }: WorkshopPanelProps) {
  const [taskInput, setTaskInput] = useState('');
  const [toolGroups, setToolGroups] = useState<ToolCallGroup[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  const [statusText, setStatusText] = useState<string>('');
  const eventSourceRef = useRef<EventSource | null>(null);
  const feedEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    feedEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [toolGroups, statusText]);

  useEffect(() => {
    return () => {
      eventSourceRef.current?.close();
    };
  }, []);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 160)}px`;
    }
  }, [taskInput]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!taskInput.trim() || streaming) return;

    const task = taskInput.trim();
    setTaskInput('');
    setToolGroups([]);
    setStatusText('');
    setStreaming(true);

    // Create conversation if needed
    let convId = conversationId;
    if (!convId) {
      try {
        const newConv = await conversationAPI.create({
          agent_id: agentId,
          title: task.slice(0, 60),
        });
        convId = newConv.id;
        onConversationChange?.(convId);
      } catch {
        setStreaming(false);
        return;
      }
    }

    const url = conversationAPI.getStreamURL(convId);
    const eventSource = new EventSource(
      `${url}?message=${encodeURIComponent(task)}&_t=${Date.now()}`
    );
    eventSourceRef.current = eventSource;

    // Track pending calls by index so we can match results
    const pendingCalls = new Map<number, string>(); // index → group id
    let callIndex = 0;

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === 'status') {
        setStatusText(data.content);

      } else if (data.type === 'tool_call') {
        const groupId = `call-${Date.now()}-${callIndex}`;
        pendingCalls.set(callIndex, groupId);
        callIndex++;

        const group: ToolCallGroup = {
          id: groupId,
          name: data.name,
          arguments: data.arguments ?? {},
          timestamp: new Date().toISOString(),
          pending: true,
        };

        setToolGroups(prev => [...prev, group]);
        // Auto-expand the latest call
        setExpandedGroups(prev => new Set([...prev, groupId]));

      } else if (data.type === 'tool_result') {
        // Match to the oldest pending call
        const pendingIndex = [...pendingCalls.keys()].sort((a, b) => a - b)[0];
        if (pendingIndex !== undefined) {
          const groupId = pendingCalls.get(pendingIndex)!;
          pendingCalls.delete(pendingIndex);

          setToolGroups(prev => prev.map(g =>
            g.id === groupId
              ? { ...g, result: data.result, error: data.error, pending: false }
              : g
          ));
        }

      } else if (data.type === 'done' || data.type === 'error') {
        setStreaming(false);
        setStatusText('');
        eventSource.close();
      }
    };

    eventSource.onerror = () => {
      setStreaming(false);
      setStatusText('');
      eventSource.close();
    };
  };

  const toggleExpand = (id: string) => {
    setExpandedGroups(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const formatValue = (value: unknown): string => {
    if (typeof value === 'string') return value;
    return JSON.stringify(value, null, 2);
  };

  const renderArgs = (args: Record<string, unknown>) => {
    const entries = Object.entries(args);
    if (entries.length === 0) return <span className="ws-no-args">no arguments</span>;
    return (
      <div className="ws-args">
        {entries.map(([k, v]) => (
          <div key={k} className="ws-arg-row">
            <span className="ws-arg-key">{k}</span>
            <span className="ws-arg-val">{formatValue(v)}</span>
          </div>
        ))}
      </div>
    );
  };

  const renderResult = (group: ToolCallGroup) => {
    if (group.pending) {
      return <div className="ws-result-pending"><span className="ws-spinner" />running…</div>;
    }
    if (group.error) {
      return <div className="ws-result-error">{group.error}</div>;
    }
    const text = formatValue(group.result);
    return <pre className="ws-result-content">{text}</pre>;
  };

  return (
    <div className="workshop-panel">
      {/* Task input */}
      <form className="ws-task-form" onSubmit={handleSubmit}>
        <textarea
          ref={textareaRef}
          className="ws-task-input"
          placeholder="Give Kevin a task…"
          value={taskInput}
          onChange={e => setTaskInput(e.target.value)}
          disabled={streaming}
          onKeyDown={e => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSubmit(e as unknown as React.FormEvent);
            }
          }}
          rows={1}
        />
        <button
          type="submit"
          className="ws-send-button"
          disabled={!taskInput.trim() || streaming}
        >
          {streaming ? '…' : '▶'}
        </button>
      </form>

      {/* Tool call feed */}
      <div className="ws-feed">
        {toolGroups.length === 0 && !streaming && (
          <div className="ws-empty">
            Tool calls will appear here as Kevin works.
          </div>
        )}

        {statusText && (
          <div className="ws-status">{statusText}</div>
        )}

        {toolGroups.map(group => {
          const expanded = expandedGroups.has(group.id);
          return (
            <div
              key={group.id}
              className={`ws-group ${group.pending ? 'pending' : ''} ${group.error ? 'errored' : ''}`}
            >
              {/* Header row — always visible */}
              <button
                className="ws-group-header"
                onClick={() => toggleExpand(group.id)}
              >
                <span className="ws-chevron">{expanded ? '▾' : '▸'}</span>
                <span className="ws-tool-name">{group.name}</span>
                {group.pending && <span className="ws-badge pending">running</span>}
                {!group.pending && !group.error && <span className="ws-badge done">done</span>}
                {group.error && <span className="ws-badge error">error</span>}
                <span className="ws-timestamp">
                  {new Date(group.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                </span>
              </button>

              {/* Expandable body */}
              {expanded && (
                <div className="ws-group-body">
                  <div className="ws-section-label">Input</div>
                  {renderArgs(group.arguments)}
                  <div className="ws-section-label" style={{ marginTop: '10px' }}>Output</div>
                  {renderResult(group)}
                </div>
              )}
            </div>
          );
        })}

        <div ref={feedEndRef} />
      </div>
    </div>
  );
}

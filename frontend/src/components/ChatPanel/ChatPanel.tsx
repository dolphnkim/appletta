import { useState, useEffect, useRef } from 'react';
import { conversationAPI } from '../../api/conversationAPI';
import ContextWindowModal from './ContextWindowModal';
import ContextWindowIndicator from './ContextWindowIndicator';
import type { Agent } from '../../types/agent';
import type { Conversation, Message } from '../../types/conversation';
import './ChatPanel.css';

interface ChatPanelProps {
  agentId: string;
  agents: Agent[];
  conversationId?: string;
  onConversationChange?: (conversationId: string) => void;
  onAgentChange: (agentId: string) => void;
}

export default function ChatPanel({ agentId, agents, conversationId, onConversationChange, onAgentChange }: ChatPanelProps) {
  const [currentConversation, setCurrentConversation] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [editingMessageId, setEditingMessageId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState('');
  const [showContextWindow, setShowContextWindow] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Load conversation when conversationId changes
  useEffect(() => {
    if (conversationId) {
      loadConversation(conversationId);
      loadMessages(conversationId);
    } else {
      setCurrentConversation(null);
      setMessages([]);
    }
  }, [conversationId]);

  // Auto-scroll to bottom when messages change or streaming
  useEffect(() => {
    scrollToBottom();
  }, [messages, streamingContent]);

  // Cleanup EventSource on unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const loadConversation = async (convId: string) => {
    try {
      const data = await conversationAPI.get(convId);
      setCurrentConversation(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load conversation');
    }
  };

  const loadMessages = async (convId: string) => {
    try {
      const data = await conversationAPI.getMessages(convId);
      setMessages(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load messages');
    }
  };

  const createNewConversation = async () => {
    try {
      const newConv = await conversationAPI.create({
        agent_id: agentId,
        title: 'New Conversation',
      });
      setCurrentConversation(newConv);
      setMessages([]);
      onConversationChange?.(newConv.id);
      return newConv.id;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create conversation');
      return null;
    }
  };

  const sendMessage = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!inputValue.trim() || streaming) return;

    // Create conversation if none exists
    let convId: string | null | undefined = conversationId;
    if (!convId) {
      convId = await createNewConversation();
      if (!convId) return;
    }

    const messageContent = inputValue.trim();
    setInputValue('');
    setError(null);

    // Use streaming if available
    await sendStreamingMessage(convId, messageContent);

    // Keep focus on input after sending
    setTimeout(() => {
      inputRef.current?.focus();
    }, 100);
  };

  const sendStreamingMessage = async (convId: string, content: string) => {
    setStreaming(true);
    setStreamingContent('');

    // Add user message immediately
    const tempUserMessage: Message = {
      id: 'temp-user',
      conversation_id: convId,
      role: 'user',
      content,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, tempUserMessage]);

    const url = conversationAPI.getStreamURL(convId);
    const eventSource = new EventSource(`${url}?message=${encodeURIComponent(content)}`);
    eventSourceRef.current = eventSource;

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === 'content') {
        setStreamingContent((prev) => prev + data.content);
      } else if (data.type === 'done') {
        // Stream complete - replace temp messages with real ones
        setMessages((prev) => {
          const withoutTemp = prev.filter((m) => m.id !== 'temp-user');
          return [...withoutTemp, data.user_message, data.assistant_message];
        });
        setStreamingContent('');
        setStreaming(false);
        eventSource.close();
      } else if (data.type === 'error') {
        setError(data.error);
        setStreamingContent('');
        setStreaming(false);
        eventSource.close();
      }
    };

    eventSource.onerror = () => {
      setError('Connection lost. Please try again.');
      setStreamingContent('');
      setStreaming(false);
      eventSource.close();
    };
  };

  const handleEditMessage = (message: Message) => {
    setEditingMessageId(message.id);
    setEditContent(message.content);
  };

  const handleSaveEdit = async (messageId: string) => {
    if (!conversationId) return;

    try {
      await conversationAPI.editMessage(conversationId, messageId, editContent);
      await loadMessages(conversationId);
      setEditingMessageId(null);
      setEditContent('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to edit message');
    }
  };

  const handleCancelEdit = () => {
    setEditingMessageId(null);
    setEditContent('');
  };

  const handleRegenerate = async (messageId: string) => {
    if (!conversationId) return;

    try {
      setStreaming(true);
      const response = await conversationAPI.regenerateMessage(conversationId, messageId);
      await loadMessages(conversationId);
      setStreaming(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to regenerate message');
      setStreaming(false);
    }
  };

  const handleFork = async (messageId: string) => {
    if (!conversationId) return;

    try {
      const newConv = await conversationAPI.forkConversation(conversationId, messageId);
      onConversationChange?.(newConv.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fork conversation');
    }
  };

  const handleCopy = (content: string) => {
    conversationAPI.copyMessage(content);
    // Could show a toast notification here
  };

  const formatTime = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
  };

  return (
    <div className="chat-panel">
      {/* Header */}
      <div className="chat-header">
        <div className="chat-header-title">
          {currentConversation ? currentConversation.title : 'Chat'}
        </div>
        <div className="chat-header-actions">
          <ContextWindowIndicator
            agentId={agentId}
            conversationId={conversationId}
            onClick={() => setShowContextWindow(true)}
          />
          <select
            className="agent-selector"
            value={agentId}
            onChange={(e) => onAgentChange(e.target.value)}
            title="Select agent"
          >
            {agents.map(agent => (
              <option key={agent.id} value={agent.id}>
                {agent.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {error && (
        <div className="error-banner">
          {error}
          <button onClick={() => setError(null)} className="dismiss-button">
            ×
          </button>
        </div>
      )}

      {/* Messages */}
      <div className="messages-container">
        {messages.length === 0 && !streaming ? (
          <div className="empty-chat">
            <div className="empty-icon">💬</div>
            <p>Start a conversation</p>
            <p className="hint">Send a message to begin chatting with your agent</p>
          </div>
        ) : (
          <div className="messages-list">
            {messages.map((message) => (
              <div key={message.id} className={`message message-${message.role}`}>
                {editingMessageId === message.id ? (
                  <div className="message-edit-form">
                    <textarea
                      value={editContent}
                      onChange={(e) => setEditContent(e.target.value)}
                      className="message-edit-textarea"
                      rows={4}
                    />
                    <div className="message-edit-actions">
                      <button onClick={() => handleSaveEdit(message.id)} className="btn-save">
                        Save
                      </button>
                      <button onClick={handleCancelEdit} className="btn-cancel">
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="message-header">
                      <span className="message-role">
                        {message.role === 'user' ? '👤 You' : '🤖 Assistant'}
                      </span>
                      <span className="message-time">{formatTime(message.created_at)}</span>
                    </div>
                    <div className="message-content">{message.content}</div>
                    <div className="message-actions">
                      {message.role === 'user' && (
                        <button
                          onClick={() => handleEditMessage(message)}
                          className="action-button"
                          title="Edit message"
                        >
                          ✏️
                        </button>
                      )}
                      {message.role === 'assistant' && (
                        <button
                          onClick={() => handleRegenerate(message.id)}
                          className="action-button"
                          title="Regenerate response"
                          disabled={streaming}
                        >
                          🔄
                        </button>
                      )}
                      <button
                        onClick={() => handleCopy(message.content)}
                        className="action-button"
                        title="Copy to clipboard"
                      >
                        📋
                      </button>
                      <button
                        onClick={() => handleFork(message.id)}
                        className="action-button"
                        title="Fork conversation from here"
                      >
                        🔀
                      </button>
                    </div>
                  </>
                )}
              </div>
            ))}

            {/* Streaming message */}
            {streaming && streamingContent && (
              <div className="message message-assistant streaming">
                <div className="message-header">
                  <span className="message-role">🤖 Assistant</span>
                  <span className="message-time">Streaming...</span>
                </div>
                <div className="message-content">{streamingContent}</div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Input */}
      <div className="chat-input-container">
        <form onSubmit={sendMessage} className="chat-input-form">
          <textarea
            ref={inputRef}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage(e);
              }
            }}
            placeholder="Type a message..."
            className="chat-input"
            rows={1}
            disabled={streaming}
          />
          <button
            type="submit"
            className="send-button"
            disabled={!inputValue.trim() || streaming}
          >
            {streaming ? '⟳' : '↑'}
          </button>
        </form>
        <div className="input-hint">Press Enter to send, Shift+Enter for new line</div>
      </div>

      {/* Context Window Modal */}
      {showContextWindow && (
        <ContextWindowModal
          agentId={agentId}
          conversationId={conversationId}
          onClose={() => setShowContextWindow(false)}
        />
      )}
    </div>
  );
}

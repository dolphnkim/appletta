import React, { useState, useEffect, useRef } from 'react';
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
  const [memoryNarrative, setMemoryNarrative] = useState<string>('');
  const [savedMemoryNarratives, setSavedMemoryNarratives] = useState<Array<{id: string, content: string, collapsed: boolean}>>([]);
  const [error, setError] = useState<string | null>(null);
  const [editingMessageId, setEditingMessageId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState('');
  const [showContextWindow, setShowContextWindow] = useState(false);
  const [userName, setUserName] = useState<string>(() => localStorage.getItem('userName') || 'You');
  const [isEditingUserName, setIsEditingUserName] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Get current agent name
  const currentAgent = agents.find(a => a.id === agentId);
  const agentName = currentAgent?.name || 'Assistant';

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

  // Auto-resize textarea based on content
  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.style.height = 'auto';
      inputRef.current.style.height = `${Math.min(inputRef.current.scrollHeight, 200)}px`;
    }
  }, [inputValue]);

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
    setMemoryNarrative('');

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
    // Add timestamp to prevent browser caching of EventSource GET requests
    const timestamp = Date.now();
    const eventSource = new EventSource(`${url}?message=${encodeURIComponent(content)}&_t=${timestamp}`);
    eventSourceRef.current = eventSource;

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === 'memory_narrative') {
        setMemoryNarrative(data.content);
      } else if (data.type === 'content') {
        setStreamingContent((prev) => prev + data.content);
      } else if (data.type === 'done') {
        // Save memory narrative if we have one
        if (memoryNarrative) {
          setSavedMemoryNarratives((prev) => [
            ...prev,
            { id: data.assistant_message.id, content: memoryNarrative, collapsed: false }
          ]);
        }

        // Stream complete - replace temp messages with real ones
        setMessages((prev) => {
          const withoutTemp = prev.filter((m) => m.id !== 'temp-user');
          return [...withoutTemp, data.user_message, data.assistant_message];
        });
        setStreamingContent('');
        setMemoryNarrative('');
        setStreaming(false);
        eventSource.close();
      } else if (data.type === 'error') {
        setError(data.error);
        setStreamingContent('');
        setMemoryNarrative('');
        setStreaming(false);
        eventSource.close();
      }
    };

    eventSource.onerror = () => {
      setError('Connection lost. Please try again.');
      setStreamingContent('');
      setMemoryNarrative('');
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

  const handleDelete = async (messageId: string) => {
    if (!conversationId) return;

    if (!confirm('Are you sure you want to delete this message?')) {
      return;
    }

    try {
      await conversationAPI.deleteMessage(conversationId, messageId);
      await loadMessages(conversationId);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete message');
    }
  };

  const stopStreaming = () => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    setStreaming(false);
    setStreamingContent('');
  };

  const handleUserNameChange = (newName: string) => {
    setUserName(newName);
    localStorage.setItem('userName', newName);
    setIsEditingUserName(false);
  };

  const toggleMemoryNarrativeCollapse = (id: string) => {
    setSavedMemoryNarratives((prev) =>
      prev.map((narrative) =>
        narrative.id === id ? { ...narrative, collapsed: !narrative.collapsed } : narrative
      )
    );
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
          {isEditingUserName ? (
            <input
              type="text"
              className="user-name-input"
              value={userName}
              onChange={(e) => setUserName(e.target.value)}
              onBlur={() => handleUserNameChange(userName)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleUserNameChange(userName);
                if (e.key === 'Escape') setIsEditingUserName(false);
              }}
              autoFocus
              placeholder="Your name"
            />
          ) : (
            <button
              className="user-name-button"
              onClick={() => setIsEditingUserName(true)}
              title="Click to change your name"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" style={{ marginRight: '4px' }}>
                <path d="M12 2.5a5.5 5.5 0 0 1 3.096 10.047 9.005 9.005 0 0 1 5.9 8.181.75.75 0 1 1-1.499.044 7.5 7.5 0 0 0-14.993 0 .75.75 0 0 1-1.5-.045 9.005 9.005 0 0 1 5.9-8.18A5.5 5.5 0 0 1 12 2.5ZM8 8a4 4 0 1 0 8 0 4 4 0 0 0-8 0Z" />
              </svg>
              {userName}
            </button>
          )}
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
              <React.Fragment key={message.id}>
                <div className={`message message-${message.role}`}>
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
                          {message.role === 'user' ? (
                            <>
                              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" style={{ marginRight: '4px', verticalAlign: 'text-bottom' }}>
                                <path d="M12 2.5a5.5 5.5 0 0 1 3.096 10.047 9.005 9.005 0 0 1 5.9 8.181.75.75 0 1 1-1.499.044 7.5 7.5 0 0 0-14.993 0 .75.75 0 0 1-1.5-.045 9.005 9.005 0 0 1 5.9-8.18A5.5 5.5 0 0 1 12 2.5ZM8 8a4 4 0 1 0 8 0 4 4 0 0 0-8 0Z" />
                              </svg>
                              {userName}
                            </>
                          ) : (
                            <>
                              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" style={{ marginRight: '4px', verticalAlign: 'text-bottom' }}>
                                <path d="M12 8.25a.75.75 0 0 1 .75.75v3.5a.75.75 0 0 1-1.5 0v-3.5a.75.75 0 0 1 .75-.75" />
                                <path d="M9.813 1h2.437a.75.75 0 0 1 .75.75V5h6.75A2.25 2.25 0 0 1 22 7.25v5.25h1.25a.75.75 0 0 1 0 1.5H22v5.75A2.25 2.25 0 0 1 19.75 22H4.25A2.25 2.25 0 0 1 2 19.75V14H.75a.75.75 0 0 1 0-1.5H2V7.25A2.25 2.25 0 0 1 4.25 5h7.25V2.5H9.813A.75.75 0 0 1 9.812 1ZM3.5 7.25v12.5c0 .414.336.75.75.75h15.5a.75.75 0 0 0 .75-.75V7.25a.75.75 0 0 0-.75-.75H4.25a.75.75 0 0 0-.75.75Z" />
                                <path d="M16 11a.75.75 0 0 1 .75.75v3.5a.75.75 0 0 0 1.5 0v-3.5a.75.75 0 0 0-1.5 0v3.5" />
                              </svg>
                              {agentName}
                            </>
                          )}
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
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                            <path d="M17.263 2.177a1.75 1.75 0 0 1 2.474 0l2.586 2.586a1.75 1.75 0 0 1 0 2.474L19.53 10.03l-.012.013L8.69 20.378a1.753 1.753 0 0 1-.699.409l-5.523 1.68a.748.748 0 0 1-.747-.188.748.748 0 0 1-.188-.747l1.673-5.5a1.75 1.75 0 0 1 .466-.756L14.476 4.963ZM4.708 16.361a.26.26 0 0 0-.067.108l-1.264 4.154 4.177-1.271a.253.253 0 0 0 .1-.059l10.273-9.806-2.94-2.939-10.279 9.813ZM19 8.44l2.263-2.262a.25.25 0 0 0 0-.354l-2.586-2.586a.25.25 0 0 0-.354 0L16.061 5.5Z" />
                          </svg>
                        </button>
                      )}
                      {message.role === 'assistant' && (
                        <button
                          onClick={() => handleRegenerate(message.id)}
                          className="action-button"
                          title="Regenerate response"
                          disabled={streaming}
                        >
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                            <path d="M3.109 5.603a9.001 9.001 0 0 1 12.728 0 .75.75 0 1 1-1.061 1.061 7.5 7.5 0 0 0-10.606 0 7.5 7.5 0 0 0 0 10.606 7.5 7.5 0 0 0 10.606 0l5.821-5.82H17.3a.75.75 0 0 1 0-1.5h4.75a1 1 0 0 1 1 1v4.75a.75.75 0 1 1-1.5 0v-3.083l-5.713 5.714A9 9 0 0 1 3.109 5.603Z" />
                          </svg>
                        </button>
                      )}
                      <button
                        onClick={() => handleCopy(message.content)}
                        className="action-button"
                        title="Copy to clipboard"
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                          <path d="M7.024 3.75c0-.966.784-1.75 1.75-1.75H20.25c.966 0 1.75.784 1.75 1.75v11.498a1.75 1.75 0 0 1-1.75 1.75H8.774a1.75 1.75 0 0 1-1.75-1.75Zm1.75-.25a.25.25 0 0 0-.25.25v11.498c0 .139.112.25.25.25H20.25a.25.25 0 0 0 .25-.25V3.75a.25.25 0 0 0-.25-.25Z" />
                          <path d="M1.995 10.749a1.75 1.75 0 0 1 1.75-1.751H5.25a.75.75 0 1 1 0 1.5H3.745a.25.25 0 0 0-.25.25L3.5 20.25c0 .138.111.25.25.25h9.5a.25.25 0 0 0 .25-.25v-1.51a.75.75 0 1 1 1.5 0v1.51A1.75 1.75 0 0 1 13.25 22h-9.5A1.75 1.75 0 0 1 2 20.25l-.005-9.501Z" />
                        </svg>
                      </button>
                      <button
                        onClick={() => handleFork(message.id)}
                        className="action-button"
                        title="Fork conversation from here"
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                          <path d="M8.75 19.25a3.25 3.25 0 1 1 6.5 0 3.25 3.25 0 0 1-6.5 0ZM15 4.75a3.25 3.25 0 1 1 6.5 0 3.25 3.25 0 0 1-6.5 0Zm-12.5 0a3.25 3.25 0 1 1 6.5 0 3.25 3.25 0 0 1-6.5 0ZM5.75 6.5a1.75 1.75 0 1 0-.001-3.501A1.75 1.75 0 0 0 5.75 6.5ZM12 21a1.75 1.75 0 1 0-.001-3.501A1.75 1.75 0 0 0 12 21Zm6.25-14.5a1.75 1.75 0 1 0-.001-3.501A1.75 1.75 0 0 0 18.25 6.5Z" />
                          <path d="M6.5 7.75v1A2.25 2.25 0 0 0 8.75 11h6.5a2.25 2.25 0 0 0 2.25-2.25v-1H19v1a3.75 3.75 0 0 1-3.75 3.75h-6.5A3.75 3.75 0 0 1 5 8.75v-1Z" />
                          <path d="M11.25 16.25v-5h1.5v5h-1.5Z" />
                        </svg>
                      </button>
                      <button
                        onClick={() => handleDelete(message.id)}
                        className="action-button delete-button"
                        title="Delete message"
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                          <path d="M16 1.75V3h5.25a.75.75 0 0 1 0 1.5H2.75a.75.75 0 0 1 0-1.5H8V1.75C8 .784 8.784 0 9.75 0h4.5C15.216 0 16 .784 16 1.75Zm-6.5 0V3h5V1.75a.25.25 0 0 0-.25-.25h-4.5a.25.25 0 0 0-.25.25ZM4.997 6.178a.75.75 0 1 0-1.493.144L4.916 20.92a1.75 1.75 0 0 0 1.742 1.58h10.684a1.75 1.75 0 0 0 1.742-1.581l1.413-14.597a.75.75 0 0 0-1.494-.144l-1.412 14.596a.25.25 0 0 1-.249.226H6.658a.25.25 0 0 1-.249-.226L4.997 6.178Z" />
                          <path d="M9.206 7.501a.75.75 0 0 1 .793.705l.5 8.5A.75.75 0 1 1 9 16.794l-.5-8.5a.75.75 0 0 1 .705-.793Zm6.293.793A.75.75 0 1 0 14 8.206l-.5 8.5a.75.75 0 0 0 1.498.088l.5-8.5Z" />
                        </svg>
                      </button>
                    </div>
                  </>
                )}
              </div>

              {/* Show saved memory narrative for this assistant message */}
              {message.role === 'assistant' && savedMemoryNarratives.find((n) => n.id === message.id) && (
                <div className="message message-memory">
                  {(() => {
                    const narrative = savedMemoryNarratives.find((n) => n.id === message.id)!;
                    return (
                      <>
                        <div className="message-header" onClick={() => toggleMemoryNarrativeCollapse(narrative.id)} style={{ cursor: 'pointer' }}>
                          <span className="message-role">
                            💭 Memory Agent {narrative.collapsed ? '▶' : '▼'}
                          </span>
                          <span className="message-time">Surfaced memories</span>
                        </div>
                        {!narrative.collapsed && (
                          <div className="message-content memory-narrative">{narrative.content}</div>
                        )}
                      </>
                    );
                  })()}
                </div>
              )}
            </React.Fragment>
            ))}

            {/* Memory narrative - show what the memory agent said */}
            {memoryNarrative && (
              <div className="message message-memory">
                <div className="message-header">
                  <span className="message-role">💭 Memory Agent</span>
                  <span className="message-time">Surfacing memories...</span>
                </div>
                <div className="message-content memory-narrative">{memoryNarrative}</div>
              </div>
            )}

            {/* Typing indicator - show while waiting for first chunk */}
            {streaming && !streamingContent && !memoryNarrative && (
              <div className="message message-assistant typing">
                <div className="message-header">
                  <span className="message-role">🤖 Assistant</span>
                  <span className="message-time">Thinking...</span>
                </div>
                <div className="message-content">
                  <div className="typing-indicator">
                    <span></span>
                    <span></span>
                    <span></span>
                  </div>
                </div>
              </div>
            )}

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
            disabled={streaming}
          />
          <button
            type={streaming ? "button" : "submit"}
            className="send-button"
            onClick={streaming ? stopStreaming : undefined}
            disabled={!streaming && !inputValue.trim()}
          >
            {streaming ? '⏹' : '↑'}
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

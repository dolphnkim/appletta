import { useState, useEffect, useRef } from 'react';
import { conversationAPI } from '../../api/conversationAPI';
import type { Conversation, Message } from '../../types/conversation';
import './ChatPanel.css';

interface ChatPanelProps {
  agentId: string;
}

export default function ChatPanel({ agentId }: ChatPanelProps) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [currentConversation, setCurrentConversation] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Load conversations on mount
  useEffect(() => {
    loadConversations();
  }, [agentId]);

  // Load messages when conversation changes
  useEffect(() => {
    if (currentConversation) {
      loadMessages(currentConversation.id);
    }
  }, [currentConversation]);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const loadConversations = async () => {
    try {
      setLoading(true);
      const data = await conversationAPI.list(agentId);
      setConversations(data);

      // Auto-select most recent conversation
      if (data.length > 0 && !currentConversation) {
        setCurrentConversation(data[0]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load conversations');
    } finally {
      setLoading(false);
    }
  };

  const loadMessages = async (conversationId: string) => {
    try {
      const data = await conversationAPI.getMessages(conversationId);
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
      setConversations([newConv, ...conversations]);
      setCurrentConversation(newConv);
      setMessages([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create conversation');
    }
  };

  const sendMessage = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!inputValue.trim() || sending) return;

    // Create conversation if none exists
    if (!currentConversation) {
      await createNewConversation();
      // Wait a bit for state to update
      await new Promise(resolve => setTimeout(resolve, 100));
      if (!currentConversation) return;
    }

    const messageContent = inputValue.trim();
    setInputValue('');
    setSending(true);
    setError(null);

    try {
      const response = await conversationAPI.sendMessage(currentConversation.id, {
        message: messageContent,
      });

      // Add both messages to the list
      setMessages([...messages, response.user_message, response.assistant_message]);

      // Reload conversations to update message count
      await loadConversations();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send message');
      // Restore input if send failed
      setInputValue(messageContent);
    } finally {
      setSending(false);
    }
  };

  const formatTime = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
  };

  if (loading) {
    return (
      <div className="chat-panel loading">
        <div>Loading conversations...</div>
      </div>
    );
  }

  return (
    <div className="chat-panel">
      {/* Header */}
      <div className="chat-header">
        <div className="chat-header-title">
          {currentConversation ? currentConversation.title : 'Chat'}
        </div>
        <button onClick={createNewConversation} className="new-chat-button">
          + New Chat
        </button>
      </div>

      {error && (
        <div className="error-banner">
          {error}
          <button onClick={() => setError(null)} className="dismiss-button">×</button>
        </div>
      )}

      {/* Messages */}
      <div className="messages-container">
        {messages.length === 0 ? (
          <div className="empty-chat">
            <div className="empty-icon">💬</div>
            <p>Start a conversation</p>
            <p className="hint">Send a message to begin chatting with your agent</p>
          </div>
        ) : (
          <div className="messages-list">
            {messages.map((message) => (
              <div key={message.id} className={`message message-${message.role}`}>
                <div className="message-header">
                  <span className="message-role">
                    {message.role === 'user' ? '👤 You' : '🤖 Assistant'}
                  </span>
                  <span className="message-time">{formatTime(message.created_at)}</span>
                </div>
                <div className="message-content">{message.content}</div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Input */}
      <div className="chat-input-container">
        <form onSubmit={sendMessage} className="chat-input-form">
          <textarea
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage(e);
              }
            }}
            placeholder={currentConversation ? "Type a message..." : "Create a conversation to start chatting"}
            className="chat-input"
            rows={1}
            disabled={sending}
          />
          <button
            type="submit"
            className="send-button"
            disabled={!inputValue.trim() || sending}
          >
            {sending ? '⟳' : '↑'}
          </button>
        </form>
        <div className="input-hint">
          Press Enter to send, Shift+Enter for new line
        </div>
      </div>
    </div>
  );
}

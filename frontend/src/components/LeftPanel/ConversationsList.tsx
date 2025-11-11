import { useState, useEffect } from 'react';
import { conversationAPI } from '../../api/conversationAPI';
import type { Conversation } from '../../types/conversation';
import './ConversationsList.css';

interface ConversationsListProps {
  agentId: string;
  currentConversationId?: string;
  onSelect?: (conversationId: string) => void;
  onNew?: () => void;
}

export default function ConversationsList({
  agentId,
  currentConversationId,
  onSelect,
  onNew,
}: ConversationsListProps) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadConversations();
  }, [agentId]);

  const loadConversations = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await conversationAPI.list(agentId);
      setConversations(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load conversations');
    } finally {
      setLoading(false);
    }
  };

  const handleNewConversation = async () => {
    try {
      const newConv = await conversationAPI.create({
        agent_id: agentId,
        title: 'New Conversation',
      });
      setConversations([newConv, ...conversations]);
      if (onNew) {
        onNew();
      }
      if (onSelect) {
        onSelect(newConv.id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create conversation');
    }
  };

  const handleDelete = async (conversationId: string, e: React.MouseEvent) => {
    e.stopPropagation();

    if (!confirm('Delete this conversation? This cannot be undone.')) {
      return;
    }

    try {
      await conversationAPI.delete(conversationId);
      setConversations(conversations.filter((c) => c.id !== conversationId));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete conversation');
    }
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;

    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  };

  if (loading) {
    return (
      <div className="conversations-list">
        <div className="conversations-loading">Loading conversations...</div>
      </div>
    );
  }

  return (
    <div className="conversations-list">
      <div className="conversations-header">
        <button onClick={handleNewConversation} className="new-conversation-button">
          + New Conversation
        </button>
      </div>

      {error && (
        <div className="conversations-error">
          {error}
          <button onClick={() => setError(null)} className="dismiss-button">
            ×
          </button>
        </div>
      )}

      <div className="conversations-items">
        {conversations.length === 0 ? (
          <div className="conversations-empty">
            <div className="empty-icon">💬</div>
            <p>No conversations yet</p>
            <p className="hint">Create one to get started</p>
          </div>
        ) : (
          conversations.map((conversation) => (
            <div
              key={conversation.id}
              className={`conversation-item ${
                conversation.id === currentConversationId ? 'active' : ''
              }`}
              onClick={() => onSelect?.(conversation.id)}
            >
              <div className="conversation-item-header">
                <div className="conversation-title">{conversation.title || 'Untitled'}</div>
                <button
                  onClick={(e) => handleDelete(conversation.id, e)}
                  className="conversation-delete"
                  title="Delete conversation"
                >
                  ×
                </button>
              </div>
              <div className="conversation-meta">
                <span className="conversation-message-count">
                  {conversation.message_count} {conversation.message_count === 1 ? 'message' : 'messages'}
                </span>
                <span className="conversation-date">{formatDate(conversation.updated_at)}</span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

import { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { contextWindowAPI, type ContextWindowBreakdown } from '../../api/contextWindowAPI';
import './ContextWindowModal.css';

interface ContextWindowModalProps {
  agentId: string;
  conversationId?: string;
  onClose: () => void;
}

export default function ContextWindowModal({
  agentId,
  conversationId,
  onClose,
}: ContextWindowModalProps) {
  const [data, setData] = useState<ContextWindowBreakdown | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        let breakdown: ContextWindowBreakdown;
        if (conversationId) {
          breakdown = await contextWindowAPI.getBreakdown(conversationId);
        } else {
          breakdown = await contextWindowAPI.getAgentBreakdown(agentId);
        }
        setData(breakdown);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load context window');
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [agentId, conversationId]);

  useEffect(() => {
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = '';
    };
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      onClose();
    }
  };

  return createPortal(
    <div className="modal-overlay" onClick={onClose} onKeyDown={handleKeyDown}>
      <div className="context-window-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Context Window</h2>
          <button className="modal-close" onClick={onClose} title="Close">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
              <path d="M3.72 3.72a.75.75 0 0 1 1.06 0L8 6.94l3.22-3.22a.749.749 0 0 1 1.275.326.749.749 0 0 1-.215.734L9.06 8l3.22 3.22a.749.749 0 0 1-.326 1.275.749.749 0 0 1-.734-.215L8 9.06l-3.22 3.22a.751.751 0 0 1-1.042-.018.751.751 0 0 1-.018-1.042L6.94 8 3.72 4.78a.75.75 0 0 1 0-1.06Z" />
            </svg>
          </button>
        </div>

        <div className="modal-content">
          {loading && (
            <div className="loading-state">Loading context window...</div>
          )}

          {error && (
            <div className="error-state">{error}</div>
          )}

          {data && (
            <>
              <div className="context-summary">
                <div className="summary-stat">
                  <span className="stat-label">Total Tokens:</span>
                  <span className="stat-value">{data.total_tokens.toLocaleString()}</span>
                </div>
                <div className="summary-stat">
                  <span className="stat-label">Max Tokens:</span>
                  <span className="stat-value">{data.max_context_tokens.toLocaleString()}</span>
                </div>
                <div className="summary-stat">
                  <span className="stat-label">Usage:</span>
                  <span className="stat-value">{data.percentage_used.toFixed(1)}%</span>
                </div>
              </div>

              <div className="visual-breakdown">
                <div className="breakdown-bar">
                  {data.sections
                    .filter(section => !section.name.toLowerCase().includes('available'))
                    .map((section, index) => (
                      <div
                        key={index}
                        className={`bar-segment section-${index}`}
                        style={{ width: `${section.percentage}%` }}
                        title={`${section.name}: ${section.tokens} tokens (${section.percentage.toFixed(1)}%)`}
                      />
                    ))}
                </div>
              </div>

              <div className="sections-list">
                {data.sections.map((section, index) => (
                  <div key={index} className="section-item">
                    <div className="section-header">
                      <div className="section-info">
                        <div className={`section-color section-${index}`}></div>
                        <span className="section-name">{section.name}</span>
                      </div>
                      <div className="section-stats">
                        <span className="section-tokens">{section.tokens} tokens</span>
                        <span className="section-percentage">({section.percentage.toFixed(1)}%)</span>
                      </div>
                    </div>
                    {section.content && (
                      <div className="section-content">
                        <pre>{section.content}</pre>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </>
          )}
        </div>

        <div className="modal-footer">
          <button className="button button-primary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}

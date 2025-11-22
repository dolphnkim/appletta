import { useState, useEffect, useCallback } from 'react';
import { contextWindowAPI, type ContextWindowBreakdown } from '../../api/contextWindowAPI';
import './ContextWindowIndicator.css';

interface ContextWindowIndicatorProps {
  agentId: string;
  conversationId?: string;
  onClick: () => void;
  refreshTrigger?: number;  // Increment this to trigger a refresh (e.g., after sending message)
}

export default function ContextWindowIndicator({
  agentId,
  conversationId,
  onClick,
  refreshTrigger = 0,
}: ContextWindowIndicatorProps) {
  const [data, setData] = useState<ContextWindowBreakdown | null>(null);

  const fetchData = useCallback(async () => {
    try {
      let breakdown: ContextWindowBreakdown;
      if (conversationId) {
        breakdown = await contextWindowAPI.getBreakdown(conversationId);
      } else {
        breakdown = await contextWindowAPI.getAgentBreakdown(agentId);
      }
      setData(breakdown);
    } catch (err) {
      console.error('Failed to load context window:', err);
    }
  }, [agentId, conversationId]);

  // Fetch on mount and when conversation/agent changes
  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Fetch when refreshTrigger changes (after sending a message)
  useEffect(() => {
    if (refreshTrigger > 0) {
      fetchData();
    }
  }, [refreshTrigger, fetchData]);

  if (!data) return null;

  // Filter out "Available" sections - only show what's used
  const usedSections = data.sections.filter(
    section => !section.name.toLowerCase().includes('available')
  );

  return (
    <div className="context-window-indicator" onClick={onClick} title="Click to view context window details">
      <div className="indicator-bars">
        {usedSections.map((section, index) => (
          <div
            key={index}
            className={`indicator-bar section-${index}`}
            style={{ width: `${section.percentage}%` }}
          />
        ))}
      </div>
      <div className="indicator-text">
        <span className="usage-percentage">{data.percentage_used.toFixed(0)}%</span>
        <span className="usage-label">Context</span>
      </div>
    </div>
  );
}

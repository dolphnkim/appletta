import { useState, useEffect } from 'react';
import { contextWindowAPI, type ContextWindowBreakdown } from '../../api/contextWindowAPI';
import './ContextWindowIndicator.css';

interface ContextWindowIndicatorProps {
  agentId: string;
  conversationId?: string;
  onClick: () => void;
}

export default function ContextWindowIndicator({
  agentId,
  conversationId,
  onClick,
}: ContextWindowIndicatorProps) {
  const [data, setData] = useState<ContextWindowBreakdown | null>(null);

  useEffect(() => {
    const fetchData = async () => {
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
    };

    fetchData();

    // Refresh every 10 seconds (was 2 seconds - too aggressive)
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, [agentId, conversationId]);

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

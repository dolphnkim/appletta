/**
 * Brain Scan - Expert Activation Heatmap Visualization
 *
 * The "AI MRI Machine" - Watch the model's brain light up in real-time!
 * Shows which experts activate for each generated token.
 */

import { useState, useEffect } from 'react';
import './BrainScan.css';

interface HeatmapData {
  filename: string;
  num_tokens: number;
  num_experts: number;
  heatmap_matrix: number[][]; // [tokens x experts]
  metadata: {
    start_time: string;
    end_time: string;
    prompt_preview: string;
    response_preview: string;
  };
  summary: any;
}

interface SessionInfo {
  filename: string;
  filepath: string;
  start_time: string;
  total_tokens: number;
  prompt_preview: string;
  agent_id?: string;
}

interface BrainScanProps {
  agentId?: string;
}

export default function BrainScan({ agentId }: BrainScanProps) {
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [selectedSession, setSelectedSession] = useState<string | null>(null);
  const [heatmapData, setHeatmapData] = useState<HeatmapData | null>(null);
  const [loading, setLoading] = useState(false);
  const [hoveredCell, setHoveredCell] = useState<{token: number, expert: number} | null>(null);

  // Fetch available sessions
  useEffect(() => {
    fetchSessions();
  }, [agentId]);

  const fetchSessions = async () => {
    try {
      const url = agentId
        ? `/api/v1/router-lens/sessions?agent_id=${agentId}&limit=20`
        : '/api/v1/router-lens/sessions?limit=20';

      const response = await fetch(url);
      const data = await response.json();
      setSessions(data.sessions || []);
    } catch (err) {
      console.error('Failed to fetch sessions:', err);
    }
  };

  const loadHeatmap = async (filename: string) => {
    setLoading(true);
    try {
      const url = agentId
        ? `/api/v1/router-lens/sessions/${filename}/heatmap?agent_id=${agentId}`
        : `/api/v1/router-lens/sessions/${filename}/heatmap`;

      const response = await fetch(url);
      const data = await response.json();
      setHeatmapData(data);
      setSelectedSession(filename);
    } catch (err) {
      console.error('Failed to load heatmap:', err);
    } finally {
      setLoading(false);
    }
  };

  // Get color for activation weight (0-1)
  const getActivationColor = (weight: number): string => {
    if (weight === 0) return '#111'; // Dark background for inactive

    // Heat map: blue (low) -> yellow -> red (high)
    const hue = (1 - weight) * 240; // 240 = blue, 0 = red
    const saturation = 100;
    const lightness = 30 + (weight * 40); // Brighter for higher activation

    return `hsl(${hue}, ${saturation}%, ${lightness}%)`;
  };

  return (
    <div className="brain-scan">
      <div className="brain-scan-header">
        <h2>🧠 AI MRI Scanner</h2>
        <p>Watch the neural network light up - expert activations over time</p>
      </div>

      {/* Session Selector */}
      <div className="session-selector">
        <h4>Select Brain Scan Session:</h4>
        {sessions.length === 0 ? (
          <div className="no-sessions">
            <p>No router logging sessions found.</p>
            <p>Enable router logging on an agent to capture brain activity!</p>
          </div>
        ) : (
          <div className="sessions-list">
            {sessions.map((session) => (
              <button
                key={session.filename}
                className={`session-item ${selectedSession === session.filename ? 'active' : ''}`}
                onClick={() => loadHeatmap(session.filename)}
              >
                <div className="session-time">{new Date(session.start_time).toLocaleString()}</div>
                <div className="session-preview">{session.prompt_preview}</div>
                <div className="session-stats">{session.total_tokens} tokens</div>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Heatmap Visualization */}
      {loading && <div className="loading">Loading brain scan...</div>}

      {heatmapData && !loading && (
        <div className="heatmap-container">
          <div className="heatmap-info">
            <h4>Brain Activity Map</h4>
            <div className="info-grid">
              <div><strong>Tokens Generated:</strong> {heatmapData.num_tokens}</div>
              <div><strong>Experts:</strong> {heatmapData.num_experts}</div>
              <div><strong>Prompt:</strong> {heatmapData.metadata.prompt_preview}</div>
            </div>
          </div>

          {/* The actual heatmap */}
          <div className="heatmap-canvas">
            <div className="heatmap-y-label">Experts →</div>
            <div className="heatmap-grid">
              {/* Y-axis labels (experts) */}
              <div className="y-axis">
                {Array.from({length: Math.min(heatmapData.num_experts, 128)}).map((_, expertIdx) => (
                  expertIdx % 8 === 0 && (
                    <div key={expertIdx} className="y-tick">{expertIdx}</div>
                  )
                ))}
              </div>

              {/* Heatmap cells */}
              <div className="heatmap-cells" style={{
                display: 'grid',
                gridTemplateColumns: `repeat(${heatmapData.num_tokens}, ${Math.max(4, Math.min(20, 600 / heatmapData.num_tokens))}px)`,
                gridTemplateRows: `repeat(${heatmapData.num_experts}, 4px)`,
                gap: '1px'
              }}>
                {heatmapData.heatmap_matrix.map((tokenRow, tokenIdx) => (
                  tokenRow.map((weight, expertIdx) => (
                    <div
                      key={`${tokenIdx}-${expertIdx}`}
                      className="heatmap-cell"
                      style={{
                        backgroundColor: getActivationColor(weight),
                        gridColumn: tokenIdx + 1,
                        gridRow: expertIdx + 1
                      }}
                      onMouseEnter={() => setHoveredCell({token: tokenIdx, expert: expertIdx})}
                      onMouseLeave={() => setHoveredCell(null)}
                      title={`Token ${tokenIdx}, Expert ${expertIdx}: ${weight.toFixed(3)}`}
                    />
                  ))
                ))}
              </div>
            </div>

            <div className="heatmap-x-label">← Time (token position) →</div>

            {/* Hover info */}
            {hoveredCell && (
              <div className="hover-info">
                <strong>Token {hoveredCell.token}</strong> | Expert {hoveredCell.expert}
                <br />
                Activation: {heatmapData.heatmap_matrix[hoveredCell.token][hoveredCell.expert].toFixed(4)}
              </div>
            )}
          </div>

          {/* Legend */}
          <div className="heatmap-legend">
            <div className="legend-label">Activation Weight:</div>
            <div className="legend-gradient" style={{
              background: 'linear-gradient(90deg, hsl(240, 100%, 30%), hsl(120, 100%, 50%), hsl(60, 100%, 50%), hsl(0, 100%, 50%))'
            }} />
            <div className="legend-labels">
              <span>0.0 (inactive)</span>
              <span>1.0 (max)</span>
            </div>
          </div>

          {/* Expert Usage Summary */}
          {heatmapData.summary && heatmapData.summary.top_experts && (
            <div className="expert-summary">
              <h4>Most Active Experts</h4>
              <div className="top-experts">
                {heatmapData.summary.top_experts.slice(0, 10).map((expert: any) => (
                  <div key={expert.expert_id} className="expert-stat">
                    <span className="expert-id">Expert {expert.expert_id}</span>
                    <div className="expert-bar" style={{
                      width: `${expert.percentage}%`,
                      backgroundColor: `hsl(${(expert.expert_id / heatmapData.num_experts) * 360}, 70%, 50%)`
                    }} />
                    <span className="expert-pct">{expert.percentage.toFixed(1)}%</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Brain Scan - Token-by-Token Expert Activation Viewer
 *
 * The "AI MRI Machine" - Navigate through each token to see which experts activate!
 * Shows expert activation patterns for individual tokens with full context.
 */

import { useState, useEffect } from 'react';
import './BrainScan.css';

interface HeatmapData {
  filename: string;
  num_tokens: number;
  num_experts: number;
  heatmap_matrix: number[][]; // [tokens x experts]
  token_texts: string[]; // Actual token strings
  metadata: {
    start_time: string;
    end_time: string;
    prompt: string; // Full prompt
    response: string; // Full response
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
  const [currentTokenIndex, setCurrentTokenIndex] = useState(0);
  const [showPrompt, setShowPrompt] = useState(true);

  // Fetch available sessions
  useEffect(() => {
    fetchSessions();
  }, [agentId]);

  // Reset token index when new session is loaded
  useEffect(() => {
    if (heatmapData) {
      setCurrentTokenIndex(0);
    }
  }, [heatmapData]);

  // Keyboard navigation
  useEffect(() => {
    const handleKeyPress = (e: KeyboardEvent) => {
      if (!heatmapData) return;

      if (e.key === 'ArrowRight') {
        goToNextToken();
      } else if (e.key === 'ArrowLeft') {
        goToPreviousToken();
      }
    };

    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
  }, [heatmapData, currentTokenIndex]);

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

  // Navigate to next/previous token
  const goToNextToken = () => {
    if (heatmapData && currentTokenIndex < heatmapData.num_tokens - 1) {
      setCurrentTokenIndex(currentTokenIndex + 1);
    }
  };

  const goToPreviousToken = () => {
    if (currentTokenIndex > 0) {
      setCurrentTokenIndex(currentTokenIndex - 1);
    }
  };

  // Get expert activations for current token
  const getCurrentTokenActivations = () => {
    if (!heatmapData) return [];

    const activations: { expertId: number; weight: number }[] = [];
    const tokenRow = heatmapData.heatmap_matrix[currentTokenIndex];

    if (tokenRow) {
      tokenRow.forEach((weight, expertId) => {
        if (weight > 0) {
          activations.push({ expertId, weight });
        }
      });
    }

    // Sort by weight descending
    return activations.sort((a, b) => b.weight - a.weight);
  };

  // Get color for activation weight (0-1)
  const getActivationColor = (weight: number): string => {
    if (weight === 0) return '#111';

    // Heat map: blue (low) -> yellow -> red (high)
    const hue = (1 - weight) * 240; // 240 = blue, 0 = red
    const saturation = 100;
    const lightness = 30 + (weight * 40);

    return `hsl(${hue}, ${saturation}%, ${lightness}%)`;
  };

  // Format token text for display
  const formatTokenText = (text: string): string => {
    // Show whitespace characters
    return text.replace(/ /g, '·').replace(/\n/g, '↵').replace(/\t/g, '→');
  };

  const currentTokenText = heatmapData?.token_texts[currentTokenIndex] || '';
  const activations = getCurrentTokenActivations();

  return (
    <div className="brain-scan">
      <div className="brain-scan-header">
        <h2>🧠 AI MRI Scanner - Token Navigation</h2>
        <p>Step through each token to see which neural experts activate in real-time</p>
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

      {/* Loading State */}
      {loading && <div className="loading">Loading brain scan...</div>}

      {/* Token Navigation View */}
      {heatmapData && !loading && (
        <div className="token-navigation-container">
          {/* Context Switcher */}
          <div className="context-switcher">
            <button
              className={showPrompt ? 'active' : ''}
              onClick={() => setShowPrompt(true)}
            >
              Prompt
            </button>
            <button
              className={!showPrompt ? 'active' : ''}
              onClick={() => setShowPrompt(false)}
            >
              Response ({heatmapData.num_tokens} tokens)
            </button>
          </div>

          {/* Context Display */}
          <div className="context-display">
            <h4>{showPrompt ? 'Prompt' : 'Model Response'}</h4>
            <div className="context-text">
              {showPrompt ? (
                heatmapData.metadata.prompt || heatmapData.metadata.prompt_preview || 'No prompt available'
              ) : (
                heatmapData.metadata.response || heatmapData.metadata.response_preview || 'No response available'
              )}
            </div>
          </div>

          {/* Token Navigator */}
          <div className="token-navigator">
            <div className="navigator-header">
              <h4>Token-by-Token Expert Activation</h4>
              <div className="token-counter">
                Token {currentTokenIndex + 1} of {heatmapData.num_tokens}
              </div>
            </div>

            {/* Current Token Display */}
            <div className="current-token-display">
              <div className="token-label">Current Token:</div>
              <div className="token-text" title={currentTokenText}>
                "{formatTokenText(currentTokenText)}"
              </div>
            </div>

            {/* Navigation Controls */}
            <div className="navigation-controls">
              <button
                className="nav-button prev"
                onClick={goToPreviousToken}
                disabled={currentTokenIndex === 0}
                title="Previous token (←)"
              >
                ← Previous
              </button>

              <div className="token-slider">
                <input
                  type="range"
                  min="0"
                  max={heatmapData.num_tokens - 1}
                  value={currentTokenIndex}
                  onChange={(e) => setCurrentTokenIndex(parseInt(e.target.value))}
                  className="slider"
                />
              </div>

              <button
                className="nav-button next"
                onClick={goToNextToken}
                disabled={currentTokenIndex === heatmapData.num_tokens - 1}
                title="Next token (→)"
              >
                Next →
              </button>
            </div>

            {/* Expert Activations for Current Token */}
            <div className="token-expert-activations">
              <h5>Expert Activations for This Token</h5>
              {activations.length === 0 ? (
                <div className="no-activations">No expert activations recorded</div>
              ) : (
                <div className="activations-list">
                  {activations.map(({ expertId, weight }) => (
                    <div key={expertId} className="activation-row">
                      <div className="expert-label">Expert {expertId}</div>
                      <div className="activation-bar-container">
                        <div
                          className="activation-bar"
                          style={{
                            width: `${weight * 100}%`,
                            backgroundColor: getActivationColor(weight)
                          }}
                        />
                      </div>
                      <div className="activation-weight">{weight.toFixed(4)}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Activation Weight Legend */}
            <div className="activation-legend">
              <div className="legend-title">Activation Weight Scale:</div>
              <div className="legend-info">
                Higher weights = stronger expert activation for this token.
                The model routes tokens to specialized "expert" networks based on the content.
              </div>
              <div className="legend-gradient-bar">
                <div className="gradient" style={{
                  background: 'linear-gradient(90deg, hsl(240, 100%, 30%), hsl(120, 100%, 50%), hsl(60, 100%, 50%), hsl(0, 100%, 50%))'
                }} />
                <div className="gradient-labels">
                  <span>0.0 (inactive)</span>
                  <span>0.5</span>
                  <span>1.0 (max)</span>
                </div>
              </div>
            </div>
          </div>

          {/* Session Summary */}
          {heatmapData.summary && heatmapData.summary.top_experts && (
            <div className="session-summary">
              <h4>Overall Session Statistics</h4>
              <div className="summary-stats">
                <div className="stat">
                  <span className="stat-label">Total Tokens:</span>
                  <span className="stat-value">{heatmapData.num_tokens}</span>
                </div>
                <div className="stat">
                  <span className="stat-label">Unique Experts Used:</span>
                  <span className="stat-value">{heatmapData.summary.unique_experts_used || 'N/A'}</span>
                </div>
                <div className="stat">
                  <span className="stat-label">Mean Entropy:</span>
                  <span className="stat-value">
                    {heatmapData.summary.mean_token_entropy?.toFixed(3) || 'N/A'}
                  </span>
                </div>
              </div>

              <div className="top-experts-summary">
                <h5>Most Active Experts (Overall)</h5>
                <div className="experts-grid">
                  {heatmapData.summary.top_experts.slice(0, 8).map((expert: any) => (
                    <div key={expert.expert_id} className="expert-summary-item">
                      <div className="expert-id">E{expert.expert_id}</div>
                      <div className="expert-percentage">{expert.percentage.toFixed(1)}%</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Keyboard Navigation Hint */}
      {heatmapData && (
        <div className="keyboard-hint">
          💡 Tip: Use ← and → arrow keys to navigate between tokens
        </div>
      )}
    </div>
  );
}
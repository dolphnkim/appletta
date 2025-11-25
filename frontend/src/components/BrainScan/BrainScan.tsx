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
  const [showPrompt, setShowPrompt] = useState(true); // For navigation mode only
  const [isEditing, setIsEditing] = useState(false);
  const [editedPrompt, setEditedPrompt] = useState('');
  const [editedResponse, setEditedResponse] = useState('');
  const [viewMode, setViewMode] = useState<'navigation' | 'heatmap'>('heatmap');
  const [intensityMetric, setIntensityMetric] = useState<'cognitive_load' | 'max_weight' | 'entropy'>('cognitive_load');

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
    setIsEditing(false); // Reset edit mode when loading new session
    try {
      const url = agentId
        ? `/api/v1/router-lens/sessions/${filename}/heatmap?agent_id=${agentId}`
        : `/api/v1/router-lens/sessions/${filename}/heatmap`;

      const response = await fetch(url);
      const data = await response.json();
      setHeatmapData(data);
      setSelectedSession(filename);
      // Initialize edited text with current values
      setEditedPrompt(data.metadata.prompt || data.metadata.prompt_preview || '');
      setEditedResponse(data.metadata.response || data.metadata.response_preview || '');
    } catch (err) {
      console.error('Failed to load heatmap:', err);
    } finally {
      setLoading(false);
    }
  };

  // Toggle edit mode
  const toggleEditMode = () => {
    if (!isEditing) {
      // Entering edit mode - initialize with current text
      setEditedPrompt(heatmapData?.metadata.prompt || heatmapData?.metadata.prompt_preview || '');
      setEditedResponse(heatmapData?.metadata.response || heatmapData?.metadata.response_preview || '');
    }
    setIsEditing(!isEditing);
  };

  // Save edits
  const saveEdits = () => {
    if (heatmapData) {
      setHeatmapData({
        ...heatmapData,
        metadata: {
          ...heatmapData.metadata,
          prompt: editedPrompt,
          response: editedResponse
        }
      });
    }
    setIsEditing(false);
  };

  // Cancel edits
  const cancelEdits = () => {
    setEditedPrompt(heatmapData?.metadata.prompt || heatmapData?.metadata.prompt_preview || '');
    setEditedResponse(heatmapData?.metadata.response || heatmapData?.metadata.response_preview || '');
    setIsEditing(false);
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

    const activations: { expertId: number; weight: number; percentage: number }[] = [];
    const tokenRow = heatmapData.heatmap_matrix[currentTokenIndex];

    if (tokenRow) {
      // Calculate total weight for normalization
      const totalWeight = tokenRow.reduce((sum, w) => sum + w, 0);

      tokenRow.forEach((weight, expertId) => {
        if (weight > 0) {
          // Convert to percentage of total
          const percentage = totalWeight > 0 ? (weight / totalWeight) * 100 : 0;
          activations.push({ expertId, weight, percentage });
        }
      });
    }

    // Sort by percentage descending and take only top 8
    return activations.sort((a, b) => b.percentage - a.percentage).slice(0, 8);
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

  // Get current token text with fallback
  const getCurrentTokenText = (): string => {
    if (!heatmapData) return '';
    const tokenText = heatmapData.token_texts[currentTokenIndex] || '';

    // If it's a placeholder like "layer_0", show the token index instead
    if (tokenText.startsWith('layer_')) {
      return `Token #${currentTokenIndex}`;
    }

    return tokenText;
  };

  // Calculate cognitive intensity for a token
  const calculateTokenIntensity = (tokenIndex: number): number => {
    if (!heatmapData || tokenIndex >= heatmapData.heatmap_matrix.length) return 0;

    const tokenRow = heatmapData.heatmap_matrix[tokenIndex];

    switch (intensityMetric) {
      case 'cognitive_load':
        // Number of active experts / total experts
        const activeExperts = tokenRow.filter(w => w > 0).length;
        return activeExperts / heatmapData.num_experts;

      case 'max_weight':
        // Maximum activation weight for this token
        return Math.max(...tokenRow);

      case 'entropy':
        // Calculate entropy of expert distribution (higher = more uncertain/complex)
        const activeWeights = tokenRow.filter(w => w > 0);
        if (activeWeights.length === 0) return 0;

        const sum = activeWeights.reduce((a, b) => a + b, 0);
        const probs = activeWeights.map(w => w / sum);
        const entropy = -probs.reduce((acc, p) => acc + (p > 0 ? p * Math.log2(p) : 0), 0);

        // Normalize entropy to 0-1 range (max entropy for 8 experts ≈ 3)
        return Math.min(entropy / 3, 1);

      default:
        return 0;
    }
  };

  // Get color for intensity heatmap
  const getIntensityColor = (intensity: number): string => {
    // Gradient from transparent -> yellow -> orange -> red
    if (intensity < 0.2) return `rgba(255, 255, 0, ${intensity * 2})`; // Yellow
    if (intensity < 0.5) return `rgba(255, 200, 0, ${intensity})`; // Orange-yellow
    if (intensity < 0.8) return `rgba(255, 100, 0, ${intensity})`; // Orange
    return `rgba(255, 0, 0, ${Math.min(intensity, 1)})`; // Red
  };

  const currentTokenText = getCurrentTokenText();
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
          {/* View Mode Switcher */}
          <div className="view-mode-switcher">
            <button
              className={viewMode === 'heatmap' ? 'active' : ''}
              onClick={() => setViewMode('heatmap')}
            >
              🔥 Cognitive Heatmap
            </button>
            <button
              className={viewMode === 'navigation' ? 'active' : ''}
              onClick={() => setViewMode('navigation')}
            >
              🧭 Token Navigator
            </button>
          </div>

          {/* Metric Selector (only in heatmap mode) */}
          {viewMode === 'heatmap' && (
            <div className="metric-selector">
              <label>Intensity Metric:</label>
              <select
                value={intensityMetric}
                onChange={(e) => setIntensityMetric(e.target.value as any)}
                className="metric-dropdown"
              >
                <option value="cognitive_load">Cognitive Load (# of experts)</option>
                <option value="max_weight">Maximum Activation</option>
                <option value="entropy">Uncertainty/Complexity (entropy)</option>
              </select>
            </div>
          )}

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

          {/* Cognitive Intensity Heatmap View */}
          {viewMode === 'heatmap' && (
            <div className="cognitive-heatmap-container">
              <div className="heatmap-header">
                <h4>Cognitive Intensity Heatmap</h4>
                <div className="heatmap-legend">
                  <span>Low</span>
                  <div className="legend-gradient" />
                  <span>High</span>
                </div>
              </div>

              <div className="heatmap-text">
                {showPrompt ? (
                  <div className="heatmap-prompt-message">
                    <p>Prompt text (expert activations not captured during prefill):</p>
                    <div className="context-text">
                      {heatmapData.metadata.prompt || heatmapData.metadata.prompt_preview || 'No prompt available'}
                    </div>
                  </div>
                ) : (
                  heatmapData.token_texts.map((token, idx) => {
                    const intensity = calculateTokenIntensity(idx);
                    const color = getIntensityColor(intensity);

                    return (
                      <span
                        key={idx}
                        className={`heatmap-token ${currentTokenIndex === idx ? 'selected' : ''}`}
                        style={{ backgroundColor: color }}
                        onClick={() => setCurrentTokenIndex(idx)}
                        title={`Token ${idx}: ${token}\nIntensity: ${(intensity * 100).toFixed(1)}%`}
                      >
                        {token}
                      </span>
                    );
                  })
                )}
              </div>

              {/* Selected Token Details */}
              <div className="selected-token-details">
                <h5>Selected Token: "{currentTokenText}"</h5>
                <div className="token-metrics">
                  <div className="metric">
                    <span className="metric-label">Cognitive Load:</span>
                    <span className="metric-value">
                      {(calculateTokenIntensity(currentTokenIndex) * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="metric">
                    <span className="metric-label">Active Experts:</span>
                    <span className="metric-value">
                      {activations.length} / {heatmapData.num_experts}
                    </span>
                  </div>
                  <div className="metric">
                    <span className="metric-label">Top Expert:</span>
                    <span className="metric-value">
                      {activations.length > 0 ? `Expert ${activations[0].expertId}` : 'None'}
                    </span>
                  </div>
                </div>

                <div className="token-expert-activations">
                  <h6>Top Expert Activations:</h6>
                  {activations.length === 0 ? (
                    <div className="no-activations">No expert activations</div>
                  ) : (
                    <div className="activations-list">
                      {activations.map(({ expertId, percentage }) => (
                        <div key={expertId} className="activation-row">
                          <div className="expert-label">Expert {expertId}</div>
                          <div className="activation-bar-container">
                            <div
                              className="activation-bar"
                              style={{
                                width: `${percentage}%`,
                                backgroundColor: getActivationColor(percentage / 100)
                              }}
                            />
                          </div>
                          <div className="activation-weight">{percentage.toFixed(1)}%</div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Original Context Display (for navigation mode and editing) */}
          {viewMode === 'navigation' && (
            <div className="context-display">
              <div className="context-display-header">
                <h4>{showPrompt ? 'Prompt' : 'Model Response'}</h4>
                <div className="context-edit-controls">
                  {!isEditing ? (
                    <button className="edit-button" onClick={toggleEditMode}>
                      ✏️ Edit
                    </button>
                  ) : (
                    <>
                      <button className="save-button" onClick={saveEdits}>
                        ✓ Save
                      </button>
                      <button className="cancel-button" onClick={cancelEdits}>
                        ✕ Cancel
                      </button>
                    </>
                  )}
                </div>
              </div>

              {!isEditing ? (
                <div className="context-text">
                  {showPrompt ? (
                    heatmapData.metadata.prompt || heatmapData.metadata.prompt_preview || 'No prompt available'
                  ) : (
                    heatmapData.metadata.response || heatmapData.metadata.response_preview || 'No response available'
                  )}
                </div>
              ) : (
                <textarea
                  className="context-text-editor"
                  value={showPrompt ? editedPrompt : editedResponse}
                  onChange={(e) => showPrompt ? setEditedPrompt(e.target.value) : setEditedResponse(e.target.value)}
                  rows={8}
                  placeholder={showPrompt ? 'Enter prompt...' : 'Enter response...'}
                />
              )}
            </div>
          )}

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
              <h5>Top 8 Expert Activations for This Token</h5>
              {activations.length === 0 ? (
                <div className="no-activations">No expert activations recorded</div>
              ) : (
                <div className="activations-list">
                  {activations.map(({ expertId, percentage }) => (
                    <div key={expertId} className="activation-row">
                      <div className="expert-label">Expert {expertId}</div>
                      <div className="activation-bar-container">
                        <div
                          className="activation-bar"
                          style={{
                            width: `${percentage}%`,
                            backgroundColor: getActivationColor(percentage / 100)
                          }}
                        />
                      </div>
                      <div className="activation-weight">{percentage.toFixed(1)}%</div>
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
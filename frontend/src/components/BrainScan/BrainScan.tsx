/**
 * Brain Scan - Token-by-Token Expert Activation Viewer
 *
 * The "AI MRI Machine" - Navigate through each token to see which experts activate!
 * Shows expert activation patterns for individual tokens with full context.
 * 
 * METRICS EXPLAINED:
 * - Routing Confidence: How concentrated the expert selection is (high = model is "certain")
 * - Expert Contribution: Actual softmax weight sum across layers (how much work each expert did)
 * - Top-K Coverage: What % of total weight the top-k experts captured
 */

import { useState, useEffect } from 'react';
import './BrainScan.css';

interface LayerData {
  layer_idx: number;
  selected_experts: number[];
  expert_weights: number[];
  entropy: number;
}

interface TokenData {
  idx: number;
  token: string;
  layers: LayerData[];
}

interface HeatmapData {
  filename: string;
  num_tokens: number;
  num_experts: number;
  heatmap_matrix: number[][]; // [tokens x experts] - NOW: actual weight sums
  token_texts: string[];
  token_details: TokenData[]; // Full layer-by-layer data
  metadata: {
    start_time: string;
    end_time: string;
    prompt: string;
    response: string;
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
  const [isEditing, setIsEditing] = useState(false);
  const [editedPrompt, setEditedPrompt] = useState('');
  const [editedResponse, setEditedResponse] = useState('');
  const [viewMode, setViewMode] = useState<'navigation' | 'heatmap'>('heatmap');
  const [intensityMetric, setIntensityMetric] = useState<'routing_confidence' | 'top_expert_dominance' | 'expert_diversity'>('routing_confidence');

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
      if (e.key === 'ArrowRight') goToNextToken();
      else if (e.key === 'ArrowLeft') goToPreviousToken();
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
    setIsEditing(false);
    try {
      const url = agentId
        ? `/api/v1/router-lens/sessions/${filename}/heatmap?agent_id=${agentId}`
        : `/api/v1/router-lens/sessions/${filename}/heatmap`;
      const response = await fetch(url);
      const data = await response.json();
      setHeatmapData(data);
      setSelectedSession(filename);
      setEditedPrompt(data.metadata.prompt || data.metadata.prompt_preview || '');
      setEditedResponse(data.metadata.response || data.metadata.response_preview || '');
    } catch (err) {
      console.error('Failed to load heatmap:', err);
    } finally {
      setLoading(false);
    }
  };

  const toggleEditMode = () => {
    if (!isEditing) {
      setEditedPrompt(heatmapData?.metadata.prompt || heatmapData?.metadata.prompt_preview || '');
      setEditedResponse(heatmapData?.metadata.response || heatmapData?.metadata.response_preview || '');
    }
    setIsEditing(!isEditing);
  };

  const saveEdits = () => {
    if (heatmapData) {
      setHeatmapData({
        ...heatmapData,
        metadata: { ...heatmapData.metadata, prompt: editedPrompt, response: editedResponse }
      });
    }
    setIsEditing(false);
  };

  const cancelEdits = () => {
    setEditedPrompt(heatmapData?.metadata.prompt || heatmapData?.metadata.prompt_preview || '');
    setEditedResponse(heatmapData?.metadata.response || heatmapData?.metadata.response_preview || '');
    setIsEditing(false);
  };

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

  /**
   * Get expert activations for current token
   * Returns the top 8 experts with their actual contribution percentages
   * These percentages WILL sum to 100% (of the shown experts' contributions)
   */
  const getCurrentTokenActivations = () => {
    if (!heatmapData) return [];

    const tokenRow = heatmapData.heatmap_matrix[currentTokenIndex];
    if (!tokenRow) return [];

    // Collect all non-zero activations
    const activations: { expertId: number; weight: number; percentage: number }[] = [];
    
    tokenRow.forEach((weight, expertId) => {
      if (weight > 0) {
        activations.push({ expertId, weight, percentage: 0 });
      }
    });

    // Sort by weight descending
    activations.sort((a, b) => b.weight - a.weight);

    // Take top 8
    const top8 = activations.slice(0, 8);

    // Calculate percentage relative to top 8 total (so they sum to 100%)
    const top8Total = top8.reduce((sum, a) => sum + a.weight, 0);
    top8.forEach(a => {
      a.percentage = top8Total > 0 ? (a.weight / top8Total) * 100 : 0;
    });

    return top8;
  };

  /**
   * Calculate token intensity based on selected metric
   * All metrics return 0-1 range for color mapping
   */
  const calculateTokenIntensity = (tokenIndex: number): number => {
    if (!heatmapData || tokenIndex >= heatmapData.heatmap_matrix.length) return 0;

    const tokenRow = heatmapData.heatmap_matrix[tokenIndex];
    const activeWeights = tokenRow.filter(w => w > 0);
    
    if (activeWeights.length === 0) return 0;

    const totalWeight = activeWeights.reduce((a, b) => a + b, 0);
    const sortedWeights = [...activeWeights].sort((a, b) => b - a);

    switch (intensityMetric) {
      case 'routing_confidence': {
        // Higher confidence = top expert takes larger share
        // Measured as: how much of total weight is in top expert
        // Normalized: if top expert has 50%+ of weight, that's high confidence
        const topWeight = sortedWeights[0] || 0;
        const confidence = topWeight / totalWeight;
        // Scale: 0.125 (equal 8-way split) to 1.0 (single expert dominance)
        // Normalize to 0-1 range
        return Math.min((confidence - 0.125) / 0.875, 1);
      }

      case 'top_expert_dominance': {
        // How much the top 2 experts dominate vs others
        const top2Weight = (sortedWeights[0] || 0) + (sortedWeights[1] || 0);
        const dominance = top2Weight / totalWeight;
        // Normalize: 0.25 (equal 8-way) to 1.0 (top 2 dominate)
        return Math.min((dominance - 0.25) / 0.75, 1);
      }

      case 'expert_diversity': {
        // Entropy-based: higher = more experts contributing equally (more "uncertain")
        // Lower = fewer experts doing the work (more "decisive")
        // We INVERT this so red = decisive, cool = uncertain
        const probs = activeWeights.map(w => w / totalWeight);
        const entropy = -probs.reduce((acc, p) => acc + (p > 0 ? p * Math.log2(p) : 0), 0);
        // Max entropy for 8 experts = log2(8) = 3
        const normalizedEntropy = Math.min(entropy / 3, 1);
        // Invert: high entropy (uncertain) = low intensity (cool colors)
        return 1 - normalizedEntropy;
      }

      default:
        return 0;
    }
  };

  /**
   * Get color for intensity heatmap
   * Cool (blue/green) = low intensity, Warm (yellow/red) = high intensity
   */
  const getIntensityColor = (intensity: number): string => {
    if (intensity < 0.01) return 'rgba(40, 40, 40, 0.3)'; // Nearly transparent for no data
    
    // Gradient: dark blue -> teal -> yellow -> orange -> red
    if (intensity < 0.25) {
      // Blue to teal
      const t = intensity / 0.25;
      return `rgba(${Math.round(30 + t * 20)}, ${Math.round(60 + t * 140)}, ${Math.round(150 + t * 50)}, ${0.5 + intensity})`;
    } else if (intensity < 0.5) {
      // Teal to yellow
      const t = (intensity - 0.25) / 0.25;
      return `rgba(${Math.round(50 + t * 205)}, ${Math.round(200 - t * 50)}, ${Math.round(200 - t * 180)}, ${0.6 + intensity * 0.3})`;
    } else if (intensity < 0.75) {
      // Yellow to orange
      const t = (intensity - 0.5) / 0.25;
      return `rgba(255, ${Math.round(150 - t * 80)}, ${Math.round(20 - t * 20)}, ${0.8 + intensity * 0.15})`;
    } else {
      // Orange to red
      const t = (intensity - 0.75) / 0.25;
      return `rgba(255, ${Math.round(70 - t * 70)}, 0, ${0.9 + intensity * 0.1})`;
    }
  };

  /**
   * Get color for activation bar (expert contribution)
   * Uses a professional gradient from blue to purple to indicate strength
   */
  const getActivationColor = (normalizedWeight: number): string => {
    // Blue to purple gradient for expert contribution bars
    const hue = 240 - (normalizedWeight * 60); // 240 (blue) to 180 (cyan) or to purple
    const saturation = 70 + (normalizedWeight * 30);
    const lightness = 45 + (normalizedWeight * 15);
    return `hsl(${hue}, ${saturation}%, ${lightness}%)`;
  };

  const formatTokenText = (text: string): string => {
    return text.replace(/ /g, '·').replace(/\n/g, '↵').replace(/\t/g, '→');
  };

  const getCurrentTokenText = (): string => {
    if (!heatmapData) return '';
    const tokenText = heatmapData.token_texts[currentTokenIndex] || '';
    if (tokenText.startsWith('layer_')) return `Token #${currentTokenIndex}`;
    return tokenText;
  };

  const currentTokenText = getCurrentTokenText();
  const activations = getCurrentTokenActivations();

  // Calculate aggregate stats for current token
  const currentTokenStats = () => {
    if (!heatmapData) return { activeCount: 0, totalWeight: 0, topExpertShare: 0 };
    const tokenRow = heatmapData.heatmap_matrix[currentTokenIndex];
    if (!tokenRow) return { activeCount: 0, totalWeight: 0, topExpertShare: 0 };
    
    const activeWeights = tokenRow.filter(w => w > 0);
    const totalWeight = activeWeights.reduce((a, b) => a + b, 0);
    const sortedWeights = [...activeWeights].sort((a, b) => b - a);
    const topExpertShare = totalWeight > 0 ? (sortedWeights[0] || 0) / totalWeight : 0;
    
    return {
      activeCount: activeWeights.length,
      totalWeight,
      topExpertShare
    };
  };

  const stats = currentTokenStats();

  return (
    <div className="brain-scan">
      <div className="brain-scan-header">
        <h2>🧠 Neural Router Analysis</h2>
        <p>Visualize which expert networks activate for each token during generation</p>
      </div>

      {/* Session Selector */}
      <div className="session-selector">
        <h4>Select Analysis Session:</h4>
        {sessions.length === 0 ? (
          <div className="no-sessions">
            <p>No router logging sessions found.</p>
            <p>Run a diagnostic inference to capture expert routing data.</p>
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

      {loading && <div className="loading">Loading analysis data...</div>}

      {heatmapData && !loading && (
        <div className="token-navigation-container">
          {/* View Mode Switcher */}
          <div className="view-mode-switcher">
            <button
              className={viewMode === 'heatmap' ? 'active' : ''}
              onClick={() => setViewMode('heatmap')}
            >
              🔥 Token Heatmap
            </button>
            <button
              className={viewMode === 'navigation' ? 'active' : ''}
              onClick={() => setViewMode('navigation')}
            >
              🧭 Context View
            </button>
          </div>

          {/* Metric Selector */}
          {viewMode === 'heatmap' && (
            <div className="metric-selector">
              <label>Color by:</label>
              <select
                value={intensityMetric}
                onChange={(e) => setIntensityMetric(e.target.value as any)}
                className="metric-dropdown"
              >
                <option value="routing_confidence">Routing Confidence (top expert share)</option>
                <option value="top_expert_dominance">Top-2 Dominance</option>
                <option value="expert_diversity">Decisiveness (inverse entropy)</option>
              </select>
            </div>
          )}

          {/* Context Switcher */}
          <div className="context-switcher">
            <button className={showPrompt ? 'active' : ''} onClick={() => setShowPrompt(true)}>
              Prompt
            </button>
            <button className={!showPrompt ? 'active' : ''} onClick={() => setShowPrompt(false)}>
              Response ({heatmapData.num_tokens} tokens)
            </button>
          </div>

          {/* Heatmap View */}
          {viewMode === 'heatmap' && (
            <div className="cognitive-heatmap-container">
              <div className="heatmap-header">
                <h4>Token Routing Heatmap</h4>
                <div className="heatmap-legend">
                  <span>Uncertain</span>
                  <div className="legend-gradient" />
                  <span>Decisive</span>
                </div>
              </div>

              <div className="heatmap-text">
                {showPrompt ? (
                  <div className="heatmap-prompt-message">
                    <p>Prompt text (routing data captured during response generation only):</p>
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
                        title={`Token ${idx}: "${token}"\n${intensityMetric}: ${(intensity * 100).toFixed(1)}%`}
                      >
                        {token}
                      </span>
                    );
                  })
                )}
              </div>

              {/* Selected Token Details - SINGLE PANEL */}
              <div className="selected-token-details">
                <h5>Token Analysis: "{currentTokenText}"</h5>
                <div className="token-metrics">
                  <div className="metric">
                    <span className="metric-label">Routing Confidence:</span>
                    <span className="metric-value">
                      {(stats.topExpertShare * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="metric">
                    <span className="metric-label">Experts Activated:</span>
                    <span className="metric-value">
                      {stats.activeCount}
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
                  <h6>Expert Contributions (Top 8):</h6>
                  {activations.length === 0 ? (
                    <div className="no-activations">No expert activations recorded</div>
                  ) : (
                    <div className="activations-list">
                      {activations.map(({ expertId, percentage }, idx) => (
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
                  <div className="percentage-note">
                    Percentages show relative contribution among top 8 experts (sums to 100%)
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Context Display (navigation mode) */}
          {viewMode === 'navigation' && (
            <div className="context-display">
              <div className="context-display-header">
                <h4>{showPrompt ? 'Prompt' : 'Model Response'}</h4>
                <div className="context-edit-controls">
                  {!isEditing ? (
                    <button className="edit-button" onClick={toggleEditMode}>✏️ Edit</button>
                  ) : (
                    <>
                      <button className="save-button" onClick={saveEdits}>✓ Save</button>
                      <button className="cancel-button" onClick={cancelEdits}>✕ Cancel</button>
                    </>
                  )}
                </div>
              </div>
              {!isEditing ? (
                <div className="context-text">
                  {showPrompt
                    ? heatmapData.metadata.prompt || heatmapData.metadata.prompt_preview || 'No prompt available'
                    : heatmapData.metadata.response || heatmapData.metadata.response_preview || 'No response available'}
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

          {/* Token Navigator - Slider and controls */}
          <div className="token-navigator">
            <div className="navigator-header">
              <h4>Token Navigation</h4>
              <div className="token-counter">
                Token {currentTokenIndex + 1} of {heatmapData.num_tokens}
              </div>
            </div>

            <div className="current-token-display">
              <div className="token-label">Current Token:</div>
              <div className="token-text" title={currentTokenText}>
                "{formatTokenText(currentTokenText)}"
              </div>
            </div>

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
          </div>

          {/* Session Summary */}
          {heatmapData.summary && heatmapData.summary.top_experts && (
            <div className="session-summary">
              <h4>Session Overview</h4>
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
                  <span className="stat-value">{heatmapData.summary.mean_token_entropy?.toFixed(3) || 'N/A'}</span>
                </div>
              </div>
              <div className="top-experts-summary">
                <h5>Most Active Experts (Session Total)</h5>
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

      {heatmapData && (
        <div className="keyboard-hint">
          💡 Tip: Use ← and → arrow keys to navigate between tokens
        </div>
      )}
    </div>
  );
}
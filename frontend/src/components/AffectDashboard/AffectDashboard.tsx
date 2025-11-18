/**
 * Affect Dashboard - Welfare Research Visualization
 *
 * Displays affect patterns, emotional trajectories, and welfare indicators
 * for LLM welfare research and interpretability.
 */

import { useState, useEffect } from 'react';
import './AffectDashboard.css';
import {
  affectAPI,
  getValenceColor,
  getActivationColor,
  getConfidenceColor,
  getEngagementColor,
  formatValence,
  formatActivation,
  getSeverityColor,
} from '../../api/affectAPI';
import type {
  ConversationAffect,
  HeatmapData,
  AgentAffectPatterns,
} from '../../api/affectAPI';

interface AffectDashboardProps {
  conversationId?: string;
  agentId?: string;
}

export default function AffectDashboard({ conversationId, agentId }: AffectDashboardProps) {
  const [conversationAffect, setConversationAffect] = useState<ConversationAffect | null>(null);
  const [heatmapData, setHeatmapData] = useState<HeatmapData | null>(null);
  const [agentPatterns, setAgentPatterns] = useState<AgentAffectPatterns | null>(null);
  const [loading, setLoading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeView, setActiveView] = useState<'conversation' | 'agent' | 'heatmap'>('conversation');
  const [selectedMetric, setSelectedMetric] = useState<string>('valence');

  // Fetch data when conversation or agent changes
  useEffect(() => {
    if (conversationId) {
      fetchConversationData();
    }
  }, [conversationId]);

  useEffect(() => {
    if (agentId && activeView === 'agent') {
      fetchAgentPatterns();
    }
  }, [agentId, activeView]);

  const fetchConversationData = async () => {
    if (!conversationId) return;
    setLoading(true);
    setError(null);

    try {
      const [affectData, heatmap] = await Promise.all([
        affectAPI.getConversationAffect(conversationId),
        affectAPI.getHeatmapData(conversationId),
      ]);
      setConversationAffect(affectData);
      setHeatmapData(heatmap);
    } catch (err) {
      console.error('Failed to fetch affect data:', err);
      setError('Failed to load affect data');
    } finally {
      setLoading(false);
    }
  };

  const fetchAgentPatterns = async () => {
    if (!agentId) return;
    setLoading(true);
    setError(null);

    try {
      const patterns = await affectAPI.getAgentPatterns(agentId);
      setAgentPatterns(patterns);
    } catch (err) {
      console.error('Failed to fetch agent patterns:', err);
      setError('Failed to load agent patterns');
    } finally {
      setLoading(false);
    }
  };

  const runAnalysis = async () => {
    if (!conversationId) return;
    setAnalyzing(true);
    setError(null);

    try {
      await affectAPI.analyzeConversation(conversationId, agentId);
      await fetchConversationData();
    } catch (err: unknown) {
      console.error('Failed to analyze conversation:', err);
      const error = err as { message?: string };
      if (error.message?.includes('cancelled')) {
        setError('Analysis was cancelled.');
      } else {
        setError(`Analysis failed: ${error.message || 'Unknown error'}. Check that the agent is running.`);
      }
    } finally {
      setAnalyzing(false);
    }
  };

  const cancelAnalysis = async () => {
    if (!conversationId) return;

    try {
      await affectAPI.cancelAnalysis(conversationId);
      setError('Analysis cancelled.');
      setAnalyzing(false);
    } catch (err) {
      console.error('Failed to cancel analysis:', err);
    }
  };

  const getMetricColor = (metric: string, value: number | null): string => {
    if (value === null) return '#444';
    switch (metric) {
      case 'valence':
        return getValenceColor(value);
      case 'activation':
        return getActivationColor(value);
      case 'confidence':
        return getConfidenceColor(value);
      case 'engagement':
        return getEngagementColor(value);
      case 'hedging':
        return `rgb(${Math.floor(255 * value)}, ${Math.floor(180 - 80 * value)}, 50)`;
      case 'elaboration':
        return `rgb(50, ${Math.floor(150 + 105 * value)}, ${Math.floor(200 + 55 * value)})`;
      default:
        return '#888';
    }
  };

  return (
    <div className="affect-dashboard">
      <div className="affect-header">
        <h3>🎭 Affect & Welfare Dashboard</h3>
        <div className="affect-tabs">
          <button
            className={activeView === 'conversation' ? 'active' : ''}
            onClick={() => setActiveView('conversation')}
          >
            Conversation
          </button>
          <button
            className={activeView === 'heatmap' ? 'active' : ''}
            onClick={() => setActiveView('heatmap')}
          >
            Heatmap
          </button>
          {agentId && (
            <button
              className={activeView === 'agent' ? 'active' : ''}
              onClick={() => setActiveView('agent')}
            >
              Agent Patterns
            </button>
          )}
        </div>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {loading && <div className="loading-indicator">Loading affect data...</div>}

      {/* Conversation View */}
      {activeView === 'conversation' && (
        <div className="conversation-affect-view">
          {!conversationId ? (
            <div className="no-selection">Select a conversation to view affect analysis</div>
          ) : (
            <>
              <div className="analysis-controls">
                <button
                  className="btn-primary"
                  onClick={runAnalysis}
                  disabled={analyzing || loading}
                >
                  {analyzing ? 'Analyzing...' : 'Run Affect Analysis'}
                </button>
                {analyzing && (
                  <button
                    className="btn-cancel"
                    onClick={cancelAnalysis}
                    title="Cancel ongoing analysis"
                  >
                    Cancel
                  </button>
                )}
                <span className="analysis-info">
                  {conversationAffect
                    ? `${conversationAffect.analyzed_messages}/${conversationAffect.total_messages} messages analyzed`
                    : 'No data yet'}
                </span>
              </div>

              {conversationAffect?.has_affect_data && (
                <>
                  {/* Aggregate Stats */}
                  <div className="affect-stats-grid">
                    <div className="affect-stat-card">
                      <div
                        className="stat-value"
                        style={{
                          color: getValenceColor(conversationAffect.aggregates.mean_valence || 0),
                        }}
                      >
                        {(conversationAffect.aggregates.mean_valence || 0).toFixed(3)}
                      </div>
                      <div className="stat-label">Mean Valence</div>
                      <div className="stat-description">
                        {formatValence(conversationAffect.aggregates.mean_valence || 0)}
                      </div>
                    </div>
                    <div className="affect-stat-card">
                      <div
                        className="stat-value"
                        style={{
                          color: getActivationColor(conversationAffect.aggregates.mean_activation || 0),
                        }}
                      >
                        {(conversationAffect.aggregates.mean_activation || 0).toFixed(3)}
                      </div>
                      <div className="stat-label">Mean Activation</div>
                      <div className="stat-description">
                        {formatActivation(conversationAffect.aggregates.mean_activation || 0)}
                      </div>
                    </div>
                    <div className="affect-stat-card">
                      <div className="stat-value">
                        {((conversationAffect.aggregates.mean_confidence || 0.5) * 100).toFixed(0)}%
                      </div>
                      <div className="stat-label">Mean Confidence</div>
                    </div>
                    <div className="affect-stat-card">
                      <div className="stat-value">
                        {((conversationAffect.aggregates.mean_engagement || 0.5) * 100).toFixed(0)}%
                      </div>
                      <div className="stat-label">Mean Engagement</div>
                    </div>
                  </div>

                  {/* Fatigue Indicator */}
                  {conversationAffect.aggregates.fatigue && (
                    <div className="fatigue-indicator">
                      <h5>Fatigue Analysis</h5>
                      <div className="fatigue-score">
                        <div
                          className="fatigue-bar"
                          style={{
                            width: `${conversationAffect.aggregates.fatigue.fatigue_score * 100}%`,
                            backgroundColor:
                              conversationAffect.aggregates.fatigue.fatigue_score > 0.6
                                ? '#ff4444'
                                : conversationAffect.aggregates.fatigue.fatigue_score > 0.3
                                  ? '#ffaa00'
                                  : '#88cc88',
                          }}
                        />
                      </div>
                      <div className="fatigue-details">
                        <span>
                          Score: {(conversationAffect.aggregates.fatigue.fatigue_score * 100).toFixed(1)}%
                        </span>
                        <span>Confidence: {conversationAffect.aggregates.fatigue.confidence}</span>
                      </div>
                      {conversationAffect.aggregates.fatigue.metrics && (
                        <div className="fatigue-metrics">
                          <div>
                            Engagement Drop:{' '}
                            {(conversationAffect.aggregates.fatigue.metrics.engagement_drop * 100).toFixed(1)}%
                          </div>
                          <div>
                            Elaboration Drop:{' '}
                            {(conversationAffect.aggregates.fatigue.metrics.elaboration_drop * 100).toFixed(1)}%
                          </div>
                          <div>
                            Hedging Increase:{' '}
                            {conversationAffect.aggregates.fatigue.metrics.hedging_increase.toFixed(1)}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Message Trajectory */}
                  <div className="trajectory-section">
                    <h5>Affect Trajectory</h5>
                    <div className="trajectory-chart">
                      {conversationAffect.trajectory.map((msg, idx) => (
                        <div
                          key={msg.message_id}
                          className={`trajectory-point ${msg.role}`}
                          title={`${msg.role}: ${msg.content_preview}\n\nValence: ${msg.affect?.valence?.toFixed(2) || 'N/A'}\nActivation: ${msg.affect?.activation?.toFixed(2) || 'N/A'}\nEmotions: ${msg.affect?.emotions?.join(', ') || 'N/A'}`}
                        >
                          <div
                            className="valence-marker"
                            style={{
                              bottom: `${((msg.affect?.valence || 0) + 1) * 50}%`,
                              backgroundColor: msg.affect ? getValenceColor(msg.affect.valence) : '#444',
                            }}
                          />
                          <div className="msg-label">{idx + 1}</div>
                        </div>
                      ))}
                    </div>
                    <div className="trajectory-legend">
                      <span>← Negative</span>
                      <span>Valence</span>
                      <span>Positive →</span>
                    </div>
                  </div>

                  {/* Emotion Timeline */}
                  <div className="emotions-timeline">
                    <h5>Emotion Timeline</h5>
                    <div className="emotions-list">
                      {conversationAffect.trajectory
                        .filter((msg) => msg.affect && msg.affect.emotions.length > 0)
                        .slice(-10)
                        .map((msg) => (
                          <div key={msg.message_id} className="emotion-entry">
                            <span className={`role-badge ${msg.role}`}>{msg.role}</span>
                            <div className="emotion-tags">
                              {msg.affect?.emotions.map((emotion) => (
                                <span key={emotion} className="emotion-tag">
                                  {emotion}
                                </span>
                              ))}
                            </div>
                          </div>
                        ))}
                    </div>
                  </div>
                </>
              )}

              {conversationAffect && !conversationAffect.has_affect_data && (
                <div className="no-affect-data">
                  <p>No affect analysis data yet.</p>
                  <p>Click "Run Affect Analysis" to analyze the emotional content of this conversation.</p>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Heatmap View */}
      {activeView === 'heatmap' && (
        <div className="heatmap-view">
          {!heatmapData || heatmapData.message_ids.length === 0 ? (
            <div className="no-data">No heatmap data available. Run affect analysis first.</div>
          ) : (
            <>
              <div className="heatmap-controls">
                <label>Metric:</label>
                <select value={selectedMetric} onChange={(e) => setSelectedMetric(e.target.value)}>
                  <option value="valence">Valence (Positivity)</option>
                  <option value="activation">Activation (Energy)</option>
                  <option value="confidence">Confidence</option>
                  <option value="engagement">Engagement</option>
                  <option value="hedging">Hedging (Uncertainty)</option>
                  <option value="elaboration">Elaboration</option>
                </select>
              </div>

              <div className="heatmap-grid">
                <div className="heatmap-header">
                  {heatmapData.message_ids.map((id, idx) => (
                    <div
                      key={id}
                      className={`heatmap-col-header ${heatmapData.roles[idx]}`}
                      title={`Message ${idx + 1} (${heatmapData.roles[idx]})`}
                    >
                      {idx + 1}
                    </div>
                  ))}
                </div>
                <div className="heatmap-row">
                  {heatmapData.metrics[selectedMetric as keyof typeof heatmapData.metrics].map(
                    (value, idx) => (
                      <div
                        key={idx}
                        className="heatmap-cell"
                        style={{
                          backgroundColor: getMetricColor(selectedMetric, value),
                        }}
                        title={`${selectedMetric}: ${value !== null ? value.toFixed(3) : 'N/A'}`}
                      >
                        {value !== null ? value.toFixed(2) : '-'}
                      </div>
                    )
                  )}
                </div>
              </div>

              <div className="heatmap-legend">
                {selectedMetric === 'valence' && (
                  <>
                    <span style={{ color: getValenceColor(-1) }}>Negative</span>
                    <span style={{ color: getValenceColor(0) }}>Neutral</span>
                    <span style={{ color: getValenceColor(1) }}>Positive</span>
                  </>
                )}
                {selectedMetric === 'activation' && (
                  <>
                    <span style={{ color: getActivationColor(0) }}>Calm</span>
                    <span style={{ color: getActivationColor(0.5) }}>Moderate</span>
                    <span style={{ color: getActivationColor(1) }}>High</span>
                  </>
                )}
                {(selectedMetric === 'confidence' ||
                  selectedMetric === 'engagement' ||
                  selectedMetric === 'elaboration') && (
                  <>
                    <span>Low (0%)</span>
                    <span>Medium (50%)</span>
                    <span>High (100%)</span>
                  </>
                )}
                {selectedMetric === 'hedging' && (
                  <>
                    <span>Low Uncertainty</span>
                    <span>High Uncertainty</span>
                  </>
                )}
              </div>

              {/* Multi-metric overview */}
              <div className="multi-metric-heatmap">
                <h5>All Metrics Overview</h5>
                {Object.keys(heatmapData.metrics).map((metric) => (
                  <div key={metric} className="metric-row">
                    <span className="metric-name">{metric}</span>
                    <div className="metric-cells">
                      {heatmapData.metrics[metric as keyof typeof heatmapData.metrics].map(
                        (value, idx) => (
                          <div
                            key={idx}
                            className="mini-cell"
                            style={{
                              backgroundColor: getMetricColor(metric, value),
                            }}
                            title={`${metric}: ${value !== null ? value.toFixed(3) : 'N/A'}`}
                          />
                        )
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {/* Agent Patterns View */}
      {activeView === 'agent' && (
        <div className="agent-patterns-view">
          {!agentPatterns ? (
            <div className="no-data">No agent pattern data available.</div>
          ) : !agentPatterns.has_data ? (
            <div className="no-data">{agentPatterns.message}</div>
          ) : (
            <>
              <div className="agent-info">
                <h4>{agentPatterns.agent_name}</h4>
                <p>
                  Analyzed {agentPatterns.sample_size} messages across{' '}
                  {agentPatterns.conversations_analyzed} conversations
                </p>
              </div>

              {/* Pattern Stats */}
              <div className="pattern-stats">
                <div className="pattern-stat">
                  <div className="pattern-value">
                    {agentPatterns.patterns?.mean_valence.toFixed(3)}
                    <span className="pattern-std">±{agentPatterns.patterns?.valence_std.toFixed(3)}</span>
                  </div>
                  <div className="pattern-label">Average Valence</div>
                </div>
                <div className="pattern-stat">
                  <div className="pattern-value">
                    {((agentPatterns.patterns?.mean_confidence || 0.5) * 100).toFixed(0)}%
                    <span className="pattern-std">
                      ±{((agentPatterns.patterns?.confidence_std || 0) * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className="pattern-label">Average Confidence</div>
                </div>
                <div className="pattern-stat">
                  <div className="pattern-value">
                    {((agentPatterns.patterns?.mean_engagement || 0.5) * 100).toFixed(0)}%
                    <span className="pattern-std">
                      ±{((agentPatterns.patterns?.engagement_std || 0) * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className="pattern-label">Average Engagement</div>
                </div>
              </div>

              {/* Emotion Distribution */}
              {agentPatterns.emotion_distribution && (
                <div className="emotion-distribution">
                  <h5>Emotion Distribution</h5>
                  <div className="emotion-bars">
                    {agentPatterns.emotion_distribution.slice(0, 10).map(([emotion, count]) => {
                      const maxCount = agentPatterns.emotion_distribution![0][1];
                      const percentage = (count / maxCount) * 100;
                      return (
                        <div key={emotion} className="emotion-bar-row">
                          <span className="emotion-name">{emotion}</span>
                          <div className="emotion-bar-container">
                            <div className="emotion-bar-fill" style={{ width: `${percentage}%` }} />
                          </div>
                          <span className="emotion-count">{count}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Welfare Concerns */}
              {agentPatterns.potential_concerns && agentPatterns.potential_concerns.length > 0 && (
                <div className="welfare-concerns">
                  <h5>⚠️ Potential Welfare Concerns</h5>
                  <div className="concerns-list">
                    {agentPatterns.potential_concerns.map((concern, idx) => (
                      <div
                        key={idx}
                        className="concern-item"
                        style={{ borderLeftColor: getSeverityColor(concern.severity) }}
                      >
                        <div className="concern-header">
                          <span className="concern-type">{concern.type.replace(/_/g, ' ')}</span>
                          <span
                            className="concern-severity"
                            style={{ color: getSeverityColor(concern.severity) }}
                          >
                            {concern.severity}
                          </span>
                        </div>
                        <div className="concern-description">{concern.description}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {agentPatterns.potential_concerns?.length === 0 && (
                <div className="no-concerns">
                  <span>✓</span> No welfare concerns detected
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

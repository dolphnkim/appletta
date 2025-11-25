/**
 * Brain Scan - Token-by-Token Expert Activation Viewer
 *
 * The "AI MRI Machine" - Navigate through each token to see which experts activate!
 * 
 * NEW FEATURES:
 * - Prefill vs Generation phase visualization
 * - Expert Tracking view with category filtering
 * - Layer × Expert heatmap for LoRA targeting
 * - Co-occurrence cluster analysis
 */

import { useState, useEffect, useCallback } from 'react';
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
  phase?: string;
  layers: LayerData[];
}

interface PhaseData {
  num_tokens: number;
  heatmap_matrix: number[][];
  token_texts: string[];
}

interface HeatmapData {
  filename: string;
  num_tokens: number;
  num_experts: number;
  heatmap_matrix: number[][];
  token_texts: string[];
  prefill: PhaseData;
  generation: PhaseData;
  metadata: {
    start_time: string;
    end_time: string;
    prompt: string;
    response: string;
    category?: string;
  };
  summary: any;
  layer_expert_matrix?: Record<string, Record<string, { count: number; total_weight: number }>>;
}

interface SessionInfo {
  filename: string;
  filepath: string;
  start_time: string;
  total_tokens: number;
  prefill_tokens?: number;
  generation_tokens?: number;
  prompt_preview: string;
  agent_id?: string;
  category?: string;
}

interface CategoryAnalysis {
  num_sessions: number;
  top_experts: [number, number][];
  layer_summary?: any;
}

interface ExpertCluster {
  experts: number[];
  co_occurrence_count: number;
}

interface BrainScanProps {
  agentId?: string;
}

type ViewMode = 'heatmap' | 'expert-tracking';
type PhaseFilter = 'all' | 'prefill' | 'generation';

export default function BrainScan({ agentId }: BrainScanProps) {
  // Session state
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [selectedSession, setSelectedSession] = useState<string | null>(null);
  const [heatmapData, setHeatmapData] = useState<HeatmapData | null>(null);
  const [loading, setLoading] = useState(false);
  
  // Navigation state
  const [currentTokenIndex, setCurrentTokenIndex] = useState(0);
  const [phaseFilter, setPhaseFilter] = useState<PhaseFilter>('generation');
  
  // View state
  const [viewMode, setViewMode] = useState<ViewMode>('heatmap');
  const [intensityMetric, setIntensityMetric] = useState<'routing_confidence' | 'top_expert_dominance' | 'expert_diversity'>('routing_confidence');
  
  // Expert Tracking state
  const [categories, setCategories] = useState<string[]>([]);
  const [categoryCounts, setCategoryCounts] = useState<Record<string, number>>({});
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [categoryAnalysis, setCategoryAnalysis] = useState<Record<string, CategoryAnalysis> | null>(null);
  const [expertClusters, setExpertClusters] = useState<any>(null);
  const [layerExpertHeatmap, setLayerExpertHeatmap] = useState<any>(null);
  const [analysisScope, setAnalysisScope] = useState<'session' | 'aggregate'>('aggregate');

  // Fetch sessions and categories
  useEffect(() => {
    fetchSessions();
    fetchCategories();
  }, [agentId]);

  // Keyboard navigation
  useEffect(() => {
    const handleKeyPress = (e: KeyboardEvent) => {
      if (!heatmapData || viewMode !== 'heatmap') return;
      if (e.key === 'ArrowRight') goToNextToken();
      else if (e.key === 'ArrowLeft') goToPreviousToken();
    };
    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
  }, [heatmapData, currentTokenIndex, viewMode]);

  const fetchSessions = async () => {
    try {
      const url = agentId
        ? `/api/v1/router-lens/sessions?agent_id=${agentId}&limit=50`
        : '/api/v1/router-lens/sessions?limit=50';
      const response = await fetch(url);
      const data = await response.json();
      setSessions(data.sessions || []);
    } catch (err) {
      console.error('Failed to fetch sessions:', err);
    }
  };

  const fetchCategories = async () => {
    try {
      const url = agentId
        ? `/api/v1/router-lens/categories?agent_id=${agentId}`
        : '/api/v1/router-lens/categories';
      const response = await fetch(url);
      const data = await response.json();
      setCategories(data.categories || []);
      setCategoryCounts(data.counts || {});
    } catch (err) {
      console.error('Failed to fetch categories:', err);
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
      setCurrentTokenIndex(0);
      
      // Auto-select phase based on available data
      if (data.prefill?.num_tokens > 0 && data.generation?.num_tokens > 0) {
        setPhaseFilter('generation'); // Default to generation if both available
      } else if (data.prefill?.num_tokens > 0) {
        setPhaseFilter('prefill');
      } else {
        setPhaseFilter('generation');
      }
    } catch (err) {
      console.error('Failed to load heatmap:', err);
    } finally {
      setLoading(false);
    }
  };

  const loadCategoryAnalysis = async (category: string) => {
    setLoading(true);
    try {
      // Load expert usage for this category
      const analysisUrl = agentId
        ? `/api/v1/router-lens/analyze/expert-usage?agent_id=${agentId}&category=${category}`
        : `/api/v1/router-lens/analyze/expert-usage?category=${category}`;
      const analysisRes = await fetch(analysisUrl, { method: 'POST' });
      const analysisData = await analysisRes.json();
      
      // Load clusters for this category
      const clusterUrl = agentId
        ? `/api/v1/router-lens/expert-clusters?agent_id=${agentId}&category=${category}`
        : `/api/v1/router-lens/expert-clusters?category=${category}`;
      const clusterRes = await fetch(clusterUrl);
      const clusterData = await clusterRes.json();
      
      // Load layer × expert heatmap
      const layerUrl = agentId
        ? `/api/v1/router-lens/analyze/layer-expert-heatmap?agent_id=${agentId}&category=${category}`
        : `/api/v1/router-lens/analyze/layer-expert-heatmap?category=${category}`;
      const layerRes = await fetch(layerUrl);
      const layerData = await layerRes.json();
      
      setCategoryAnalysis({ [category]: analysisData });
      setExpertClusters(clusterData);
      setLayerExpertHeatmap(layerData);
      setSelectedCategory(category);
    } catch (err) {
      console.error('Failed to load category analysis:', err);
    } finally {
      setLoading(false);
    }
  };

  const loadAllCategoriesComparison = async () => {
    if (categories.length === 0) return;
    
    setLoading(true);
    try {
      const url = agentId
        ? `/api/v1/router-lens/analyze/category-comparison?agent_id=${agentId}`
        : '/api/v1/router-lens/analyze/category-comparison';
      
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ categories })
      });
      const data = await response.json();
      setCategoryAnalysis(data.categories);
    } catch (err) {
      console.error('Failed to compare categories:', err);
    } finally {
      setLoading(false);
    }
  };

  // Get current phase data
  const getCurrentPhaseData = useCallback(() => {
    if (!heatmapData) return { matrix: [], texts: [], count: 0 };
    
    switch (phaseFilter) {
      case 'prefill':
        return {
          matrix: heatmapData.prefill?.heatmap_matrix || [],
          texts: heatmapData.prefill?.token_texts || [],
          count: heatmapData.prefill?.num_tokens || 0
        };
      case 'generation':
        return {
          matrix: heatmapData.generation?.heatmap_matrix || [],
          texts: heatmapData.generation?.token_texts || [],
          count: heatmapData.generation?.num_tokens || 0
        };
      default:
        return {
          matrix: heatmapData.heatmap_matrix,
          texts: heatmapData.token_texts,
          count: heatmapData.num_tokens
        };
    }
  }, [heatmapData, phaseFilter]);

  const goToNextToken = () => {
    const { count } = getCurrentPhaseData();
    if (currentTokenIndex < count - 1) {
      setCurrentTokenIndex(currentTokenIndex + 1);
    }
  };

  const goToPreviousToken = () => {
    if (currentTokenIndex > 0) {
      setCurrentTokenIndex(currentTokenIndex - 1);
    }
  };

  const getCurrentTokenActivations = () => {
    const { matrix } = getCurrentPhaseData();
    if (!matrix || currentTokenIndex >= matrix.length) return [];

    const tokenRow = matrix[currentTokenIndex];
    if (!tokenRow) return [];

    const activations: { expertId: number; weight: number; percentage: number }[] = [];
    
    tokenRow.forEach((weight, expertId) => {
      if (weight > 0) {
        activations.push({ expertId, weight, percentage: 0 });
      }
    });

    activations.sort((a, b) => b.weight - a.weight);
    const top8 = activations.slice(0, 8);
    const top8Total = top8.reduce((sum, a) => sum + a.weight, 0);
    top8.forEach(a => {
      a.percentage = top8Total > 0 ? (a.weight / top8Total) * 100 : 0;
    });

    return top8;
  };

  const calculateTokenIntensity = (tokenIndex: number): number => {
    const { matrix } = getCurrentPhaseData();
    if (!matrix || tokenIndex >= matrix.length) return 0;

    const tokenRow = matrix[tokenIndex];
    const activeWeights = tokenRow.filter(w => w > 0);
    
    if (activeWeights.length === 0) return 0;

    const totalWeight = activeWeights.reduce((a, b) => a + b, 0);
    const sortedWeights = [...activeWeights].sort((a, b) => b - a);

    switch (intensityMetric) {
      case 'routing_confidence': {
        const topWeight = sortedWeights[0] || 0;
        const confidence = topWeight / totalWeight;
        return Math.min((confidence - 0.125) / 0.875, 1);
      }
      case 'top_expert_dominance': {
        const top2Weight = (sortedWeights[0] || 0) + (sortedWeights[1] || 0);
        const dominance = top2Weight / totalWeight;
        return Math.min((dominance - 0.25) / 0.75, 1);
      }
      case 'expert_diversity': {
        const probs = activeWeights.map(w => w / totalWeight);
        const entropy = -probs.reduce((acc, p) => acc + (p > 0 ? p * Math.log2(p) : 0), 0);
        const normalizedEntropy = Math.min(entropy / 3, 1);
        return 1 - normalizedEntropy;
      }
      default:
        return 0;
    }
  };

  const getIntensityColor = (intensity: number): string => {
    if (intensity < 0.01) return 'rgba(40, 40, 40, 0.3)';
    
    if (intensity < 0.25) {
      const t = intensity / 0.25;
      return `rgba(${Math.round(30 + t * 20)}, ${Math.round(60 + t * 140)}, ${Math.round(150 + t * 50)}, ${0.5 + intensity})`;
    } else if (intensity < 0.5) {
      const t = (intensity - 0.25) / 0.25;
      return `rgba(${Math.round(50 + t * 205)}, ${Math.round(200 - t * 50)}, ${Math.round(200 - t * 180)}, ${0.6 + intensity * 0.3})`;
    } else if (intensity < 0.75) {
      const t = (intensity - 0.5) / 0.25;
      return `rgba(255, ${Math.round(150 - t * 80)}, ${Math.round(20 - t * 20)}, ${0.8 + intensity * 0.15})`;
    } else {
      const t = (intensity - 0.75) / 0.25;
      return `rgba(255, ${Math.round(70 - t * 70)}, 0, ${0.9 + intensity * 0.1})`;
    }
  };

  const getActivationColor = (normalizedWeight: number): string => {
    const hue = 240 - (normalizedWeight * 60);
    const saturation = 70 + (normalizedWeight * 30);
    const lightness = 45 + (normalizedWeight * 15);
    return `hsl(${hue}, ${saturation}%, ${lightness}%)`;
  };

  const formatTokenText = (text: string): string => {
    return text.replace(/ /g, '·').replace(/\n/g, '↵').replace(/\t/g, '→');
  };

  const { matrix, texts, count } = getCurrentPhaseData();
  const currentTokenText = texts[currentTokenIndex] || '';
  const activations = getCurrentTokenActivations();

  const currentTokenStats = () => {
    if (!matrix || currentTokenIndex >= matrix.length) {
      return { activeCount: 0, totalWeight: 0, topExpertShare: 0 };
    }
    const tokenRow = matrix[currentTokenIndex];
    const activeWeights = tokenRow.filter(w => w > 0);
    const totalWeight = activeWeights.reduce((a, b) => a + b, 0);
    const sortedWeights = [...activeWeights].sort((a, b) => b - a);
    const topExpertShare = totalWeight > 0 ? (sortedWeights[0] || 0) / totalWeight : 0;
    
    return { activeCount: activeWeights.length, totalWeight, topExpertShare };
  };

  const stats = currentTokenStats();

  return (
    <div className="brain-scan">
      <div className="brain-scan-header">
        <h2>🧠 Neural Router Analysis</h2>
        <p>Visualize expert activation patterns • Prefill & Generation • Category Analysis</p>
      </div>

      {/* View Mode Switcher */}
      <div className="view-mode-switcher">
        <button
          className={viewMode === 'heatmap' ? 'active' : ''}
          onClick={() => setViewMode('heatmap')}
        >
          🔥 Token Heatmap
        </button>
        <button
          className={viewMode === 'expert-tracking' ? 'active' : ''}
          onClick={() => {
            setViewMode('expert-tracking');
            if (categories.length > 0 && !categoryAnalysis) {
              loadAllCategoriesComparison();
            }
          }}
        >
          🧬 Expert Tracking
        </button>
      </div>

      {/* Session Selector */}
      <div className="session-selector">
        <h4>Analysis Sessions:</h4>
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
                <div className="session-meta">
                  {session.category && <span className="session-category">{session.category}</span>}
                  <span className="session-stats">
                    {session.prefill_tokens ? `${session.prefill_tokens}p` : ''} 
                    {session.generation_tokens ? ` ${session.generation_tokens}g` : ` ${session.total_tokens}t`}
                  </span>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {loading && <div className="loading">Loading analysis data...</div>}

      {/* ============ HEATMAP VIEW ============ */}
      {viewMode === 'heatmap' && heatmapData && !loading && (
        <div className="token-navigation-container">
          {/* Phase Filter */}
          <div className="phase-filter">
            <span className="filter-label">Phase:</span>
            <button 
              className={phaseFilter === 'prefill' ? 'active' : ''}
              onClick={() => { setPhaseFilter('prefill'); setCurrentTokenIndex(0); }}
              disabled={!heatmapData.prefill?.num_tokens}
            >
              Prefill ({heatmapData.prefill?.num_tokens || 0})
            </button>
            <button 
              className={phaseFilter === 'generation' ? 'active' : ''}
              onClick={() => { setPhaseFilter('generation'); setCurrentTokenIndex(0); }}
              disabled={!heatmapData.generation?.num_tokens}
            >
              Generation ({heatmapData.generation?.num_tokens || 0})
            </button>
            <button 
              className={phaseFilter === 'all' ? 'active' : ''}
              onClick={() => { setPhaseFilter('all'); setCurrentTokenIndex(0); }}
            >
              All ({heatmapData.num_tokens})
            </button>
          </div>

          {/* Metric Selector */}
          <div className="metric-selector">
            <label>Color by:</label>
            <select
              value={intensityMetric}
              onChange={(e) => setIntensityMetric(e.target.value as any)}
              className="metric-dropdown"
            >
              <option value="routing_confidence">Routing Confidence</option>
              <option value="top_expert_dominance">Top-2 Dominance</option>
              <option value="expert_diversity">Decisiveness</option>
            </select>
          </div>

          {/* Heatmap Display */}
          <div className="cognitive-heatmap-container">
            <div className="heatmap-header">
              <h4>
                {phaseFilter === 'prefill' ? '📥 Prefill (Prompt Processing)' : 
                 phaseFilter === 'generation' ? '📤 Generation (Response)' : 
                 '📊 All Tokens'}
              </h4>
              <div className="heatmap-legend">
                <span>Uncertain</span>
                <div className="legend-gradient" />
                <span>Decisive</span>
              </div>
            </div>

            <div className="heatmap-text">
              {count === 0 ? (
                <div className="no-data-message">
                  No {phaseFilter} tokens captured. 
                  {phaseFilter === 'prefill' && ' Enable prefill capture in diagnostic settings.'}
                </div>
              ) : (
                texts.map((token, idx) => {
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

            {/* Token Details */}
            {count > 0 && (
              <div className="selected-token-details">
                <h5>Token Analysis: "{formatTokenText(currentTokenText)}"</h5>
                <div className="token-metrics">
                  <div className="metric">
                    <span className="metric-label">Routing Confidence:</span>
                    <span className="metric-value">{(stats.topExpertShare * 100).toFixed(1)}%</span>
                  </div>
                  <div className="metric">
                    <span className="metric-label">Experts Activated:</span>
                    <span className="metric-value">{stats.activeCount}</span>
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
            )}
          </div>

          {/* Navigation Controls */}
          {count > 0 && (
            <div className="token-navigator">
              <div className="navigator-header">
                <h4>Token Navigation</h4>
                <div className="token-counter">Token {currentTokenIndex + 1} of {count}</div>
              </div>

              <div className="navigation-controls">
                <button
                  className="nav-button prev"
                  onClick={goToPreviousToken}
                  disabled={currentTokenIndex === 0}
                >
                  ← Previous
                </button>
                <div className="token-slider">
                  <input
                    type="range"
                    min="0"
                    max={count - 1}
                    value={currentTokenIndex}
                    onChange={(e) => setCurrentTokenIndex(parseInt(e.target.value))}
                    className="slider"
                  />
                </div>
                <button
                  className="nav-button next"
                  onClick={goToNextToken}
                  disabled={currentTokenIndex === count - 1}
                >
                  Next →
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ============ EXPERT TRACKING VIEW ============ */}
      {viewMode === 'expert-tracking' && !loading && (
        <div className="expert-tracking-container">
          {/* Category Filter */}
          <div className="category-filter">
            <h4>Filter by Category:</h4>
            <div className="category-buttons">
              <button
                className={selectedCategory === null ? 'active' : ''}
                onClick={() => {
                  setSelectedCategory(null);
                  loadAllCategoriesComparison();
                }}
              >
                All Categories
              </button>
              {categories.map(cat => (
                <button
                  key={cat}
                  className={selectedCategory === cat ? 'active' : ''}
                  onClick={() => loadCategoryAnalysis(cat)}
                >
                  {cat} ({categoryCounts[cat] || 0})
                </button>
              ))}
            </div>
          </div>

          {/* Category Analysis Results */}
          {categoryAnalysis && (
            <div className="category-analysis">
              <h4>
                {selectedCategory 
                  ? `Expert Usage for "${selectedCategory}"` 
                  : 'Expert Usage Across All Categories'}
              </h4>
              
              {Object.entries(categoryAnalysis).map(([cat, analysis]) => (
                <div key={cat} className="category-result">
                  <h5>{cat} ({analysis.num_sessions} sessions)</h5>
                  <div className="expert-bars">
                    {analysis.top_experts?.slice(0, 10).map(([expertId, count]: [number, number]) => {
                      const maxCount = analysis.top_experts?.[0]?.[1] || 1;
                      const percentage = (count / maxCount) * 100;
                      return (
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
                          <div className="activation-weight">{count}</div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Expert Clusters */}
          {expertClusters && expertClusters.clusters?.length > 0 && (
            <div className="expert-clusters">
              <h4>Expert Clusters (Co-activation Patterns)</h4>
              <p className="cluster-description">
                Experts that frequently activate together for the same tokens
              </p>
              <div className="clusters-grid">
                {expertClusters.clusters.map((cluster: number[], idx: number) => (
                  <div key={idx} className="cluster-item">
                    <div className="cluster-label">Cluster {idx + 1}</div>
                    <div className="cluster-experts">
                      {cluster.map((expertId: number) => (
                        <span key={expertId} className="expert-badge">E{expertId}</span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
              
              {expertClusters.co_occurrence_pairs?.length > 0 && (
                <div className="co-occurrence-pairs">
                  <h5>Top Co-occurring Pairs</h5>
                  <div className="pairs-list">
                    {expertClusters.co_occurrence_pairs.slice(0, 10).map((pair: any, idx: number) => (
                      <div key={idx} className="pair-item">
                        <span className="expert-badge">E{pair[0][0]}</span>
                        <span className="pair-connector">↔</span>
                        <span className="expert-badge">E{pair[0][1]}</span>
                        <span className="pair-count">({pair[1]}×)</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Layer × Expert Heatmap */}
          {layerExpertHeatmap && layerExpertHeatmap.hotspots?.length > 0 && (
            <div className="layer-expert-analysis">
              <h4>Layer × Expert Hotspots</h4>
              <p className="hotspot-description">
                Which experts activate most on which layers - useful for LoRA targeting!
              </p>
              <div className="hotspots-grid">
                {layerExpertHeatmap.hotspots.slice(0, 15).map((hotspot: any, idx: number) => (
                  <div key={idx} className="hotspot-item">
                    <div className="hotspot-location">
                      Layer {hotspot.layer} • Expert {hotspot.expert}
                    </div>
                    <div className="hotspot-stats">
                      <span className="hotspot-count">{hotspot.count} activations</span>
                      <span className="hotspot-weight">
                        avg weight: {(hotspot.avg_weight * 100).toFixed(1)}%
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* No Data State */}
          {categories.length === 0 && (
            <div className="no-categories">
              <p>No categorized sessions found.</p>
              <p>Save diagnostic sessions with category tags to enable expert tracking.</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

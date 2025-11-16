import { useState, useEffect } from 'react';
import './TrainingPanel.css';
import { routerLensAPI } from '../../api/routerLensAPI';
import type {
  RouterLensStatus,
  SessionSummary,
  SavedSession,
  ExpertUsageAnalysis,
  EntropyAnalysis,
  DiagnosticPrompt,
} from '../../api/routerLensAPI';

interface TrainingPanelProps {
  agentId: string;
}

interface TrainingJob {
  id: string;
  name: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  config: TrainingConfig;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  metrics?: TrainingMetrics;
}

interface TrainingConfig {
  base_model: string;
  dataset_id: string;
  training_type: 'lora' | 'qlora' | 'full';
  lora_rank: number;
  lora_alpha: number;
  learning_rate: number;
  epochs: number;
  batch_size: number;
  // MoE-specific
  moe_enabled: boolean;
  target_experts?: number[];
  train_router: boolean;
  router_lr?: number;
  expert_balance_lambda?: number;
}

interface TrainingMetrics {
  current_epoch: number;
  total_epochs: number;
  loss: number;
  expert_usage?: Record<number, number>;
  router_entropy?: number;
}

interface Dataset {
  id: string;
  name: string;
  num_examples: number;
  tags: string[];
  created_at: string;
}

export default function TrainingPanel({ agentId }: TrainingPanelProps) {
  const [activeSection, setActiveSection] = useState<'datasets' | 'jobs' | 'moe-debug'>('datasets');
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [jobs, setJobs] = useState<TrainingJob[]>([]);
  const [showNewJobModal, setShowNewJobModal] = useState(false);

  // Router Lens state
  const [routerStatus, setRouterStatus] = useState<RouterLensStatus | null>(null);
  const [currentSession, setCurrentSession] = useState<SessionSummary | null>(null);
  const [savedSessions, setSavedSessions] = useState<SavedSession[]>([]);
  const [expertAnalysis, setExpertAnalysis] = useState<ExpertUsageAnalysis | null>(null);
  const [entropyAnalysis, setEntropyAnalysis] = useState<EntropyAnalysis | null>(null);
  const [diagnosticPrompts, setDiagnosticPrompts] = useState<DiagnosticPrompt[]>([]);
  const [routerLensLoading, setRouterLensLoading] = useState(false);
  const [routerLensError, setRouterLensError] = useState<string | null>(null);
  const [selectedSessionView, setSelectedSessionView] = useState<'current' | 'saved' | 'analysis'>('current');

  // Fetch Router Lens status when MoE Debug tab is active
  useEffect(() => {
    if (activeSection === 'moe-debug') {
      fetchRouterLensStatus();
      fetchDiagnosticPrompts();
      fetchSavedSessions();
    }
  }, [activeSection]);

  const fetchRouterLensStatus = async () => {
    try {
      const status = await routerLensAPI.getStatus();
      setRouterStatus(status);
    } catch (err) {
      console.error('Failed to fetch router lens status:', err);
      setRouterLensError('Failed to connect to Router Lens service');
    }
  };

  const fetchCurrentSession = async () => {
    try {
      setRouterLensLoading(true);
      const summary = await routerLensAPI.getSessionSummary();
      setCurrentSession(summary);
    } catch (err) {
      console.error('Failed to fetch session summary:', err);
    } finally {
      setRouterLensLoading(false);
    }
  };

  const fetchSavedSessions = async () => {
    try {
      const result = await routerLensAPI.listSessions(20);
      setSavedSessions(result.sessions);
    } catch (err) {
      console.error('Failed to fetch saved sessions:', err);
    }
  };

  const fetchDiagnosticPrompts = async () => {
    try {
      const result = await routerLensAPI.getDiagnosticPrompts();
      setDiagnosticPrompts(result.prompts);
    } catch (err) {
      console.error('Failed to fetch diagnostic prompts:', err);
    }
  };

  const analyzeExpertUsage = async () => {
    try {
      setRouterLensLoading(true);
      setRouterLensError(null);
      const analysis = await routerLensAPI.analyzeExpertUsage();
      setExpertAnalysis(analysis);
      setSelectedSessionView('analysis');
    } catch (err) {
      console.error('Failed to analyze expert usage:', err);
      setRouterLensError('Failed to analyze expert usage. Make sure you have saved sessions.');
    } finally {
      setRouterLensLoading(false);
    }
  };

  const analyzeEntropy = async () => {
    try {
      setRouterLensLoading(true);
      setRouterLensError(null);
      const analysis = await routerLensAPI.analyzeEntropyDistribution();
      setEntropyAnalysis(analysis);
      setSelectedSessionView('analysis');
    } catch (err) {
      console.error('Failed to analyze entropy:', err);
      setRouterLensError('Failed to analyze entropy distribution. Make sure you have saved sessions.');
    } finally {
      setRouterLensLoading(false);
    }
  };

  const resetInspector = async () => {
    try {
      setRouterLensLoading(true);
      await routerLensAPI.resetInspector(64, 8);
      await fetchRouterLensStatus();
      setCurrentSession(null);
    } catch (err) {
      console.error('Failed to reset inspector:', err);
    } finally {
      setRouterLensLoading(false);
    }
  };

  const saveCurrentSession = async () => {
    try {
      setRouterLensLoading(true);
      await routerLensAPI.saveSession('', '');
      await fetchSavedSessions();
      alert('Session saved successfully!');
    } catch (err) {
      console.error('Failed to save session:', err);
      alert('Failed to save session');
    } finally {
      setRouterLensLoading(false);
    }
  };

  // Placeholder data for now
  useEffect(() => {
    // TODO: Fetch from backend
    setDatasets([
      {
        id: '1',
        name: 'Persona Core Dataset',
        num_examples: 1247,
        tags: ['persona_core', 'soft_tone', 'friend_mode'],
        created_at: new Date().toISOString(),
      },
      {
        id: '2',
        name: 'Technical Skills',
        num_examples: 543,
        tags: ['analysis_mode', 'coding'],
        created_at: new Date().toISOString(),
      },
    ]);

    setJobs([
      {
        id: '1',
        name: 'Persona LoRA v1',
        status: 'completed',
        config: {
          base_model: 'Qwen3-MoE-3B',
          dataset_id: '1',
          training_type: 'lora',
          lora_rank: 16,
          lora_alpha: 32,
          learning_rate: 1e-4,
          epochs: 10,
          batch_size: 4,
          moe_enabled: true,
          target_experts: [2, 7, 14],
          train_router: false,
          router_lr: 1e-6,
          expert_balance_lambda: 0.01,
        },
        created_at: new Date(Date.now() - 86400000).toISOString(),
        started_at: new Date(Date.now() - 86400000).toISOString(),
        completed_at: new Date(Date.now() - 82800000).toISOString(),
        metrics: {
          current_epoch: 10,
          total_epochs: 10,
          loss: 0.342,
          expert_usage: { 2: 2341, 7: 1892, 14: 1456, 0: 234, 1: 189 },
          router_entropy: 2.34,
        },
      },
    ]);
  }, [agentId]);

  return (
    <div className="training-panel">
      <div className="training-header">
        <h3>🧪 Training Lab</h3>
        <div className="training-tabs">
          <button
            className={activeSection === 'datasets' ? 'active' : ''}
            onClick={() => setActiveSection('datasets')}
          >
            Datasets
          </button>
          <button
            className={activeSection === 'jobs' ? 'active' : ''}
            onClick={() => setActiveSection('jobs')}
          >
            Jobs
          </button>
          <button
            className={activeSection === 'moe-debug' ? 'active' : ''}
            onClick={() => setActiveSection('moe-debug')}
          >
            MoE Debug
          </button>
        </div>
      </div>

      <div className="training-content">
        {activeSection === 'datasets' && (
          <div className="datasets-section">
            <div className="section-header">
              <h4>Training Datasets</h4>
              <button className="btn-primary" onClick={() => alert('TODO: Dataset import modal')}>
                + Import Dataset
              </button>
            </div>
            <div className="dataset-list">
              {datasets.map((dataset) => (
                <div key={dataset.id} className="dataset-card">
                  <div className="dataset-name">{dataset.name}</div>
                  <div className="dataset-stats">
                    <span>{dataset.num_examples} examples</span>
                    <span className="dataset-tags">
                      {dataset.tags.map((tag) => (
                        <span key={tag} className="tag">
                          {tag}
                        </span>
                      ))}
                    </span>
                  </div>
                  <div className="dataset-actions">
                    <button onClick={() => alert('TODO: View dataset')}>View</button>
                    <button onClick={() => alert('TODO: Edit tags')}>Tags</button>
                    <button onClick={() => alert('TODO: Validate')}>Validate</button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {activeSection === 'jobs' && (
          <div className="jobs-section">
            <div className="section-header">
              <h4>Training Jobs</h4>
              <button className="btn-primary" onClick={() => setShowNewJobModal(true)}>
                + New Job
              </button>
            </div>
            <div className="job-list">
              {jobs.map((job) => (
                <div key={job.id} className="job-card">
                  <div className="job-header">
                    <span className="job-name">{job.name}</span>
                    <span className={`job-status status-${job.status}`}>{job.status}</span>
                  </div>
                  <div className="job-config">
                    <div>Base: {job.config.base_model}</div>
                    <div>Type: {job.config.training_type.toUpperCase()}</div>
                    <div>
                      LoRA r={job.config.lora_rank}, α={job.config.lora_alpha}
                    </div>
                    {job.config.moe_enabled && (
                      <div className="moe-config">
                        <div>🔀 MoE Mode</div>
                        <div>Target Experts: {job.config.target_experts?.join(', ') || 'All'}</div>
                        <div>Router Training: {job.config.train_router ? 'Yes' : 'No'}</div>
                        {job.config.expert_balance_lambda && (
                          <div>Balance λ: {job.config.expert_balance_lambda}</div>
                        )}
                      </div>
                    )}
                  </div>
                  {job.metrics && (
                    <div className="job-metrics">
                      <div>
                        Progress: {job.metrics.current_epoch}/{job.metrics.total_epochs} epochs
                      </div>
                      <div>Loss: {job.metrics.loss.toFixed(4)}</div>
                      {job.metrics.router_entropy && (
                        <div>Router Entropy: {job.metrics.router_entropy.toFixed(3)}</div>
                      )}
                      {job.metrics.expert_usage && (
                        <div className="expert-usage">
                          <div className="usage-title">Expert Usage:</div>
                          {Object.entries(job.metrics.expert_usage)
                            .sort(([, a], [, b]) => b - a)
                            .slice(0, 5)
                            .map(([expert, count]) => (
                              <div key={expert} className="usage-bar">
                                <span>E{expert}</span>
                                <div className="bar">
                                  <div
                                    className="fill"
                                    style={{
                                      width: `${(count / Math.max(...Object.values(job.metrics!.expert_usage!))) * 100}%`,
                                    }}
                                  />
                                </div>
                                <span>{count}</span>
                              </div>
                            ))}
                        </div>
                      )}
                    </div>
                  )}
                  <div className="job-actions">
                    <button onClick={() => alert('TODO: View logs')}>Logs</button>
                    <button onClick={() => alert('TODO: View checkpoints')}>Checkpoints</button>
                    {job.status === 'completed' && (
                      <button onClick={() => alert('TODO: Apply adapter')}>Apply Adapter</button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {activeSection === 'moe-debug' && (
          <div className="moe-debug-section">
            <div className="section-header">
              <h4>🔬 Router Lens</h4>
              <div className="router-lens-controls">
                <button
                  className="btn-secondary"
                  onClick={fetchCurrentSession}
                  disabled={routerLensLoading}
                >
                  Refresh Session
                </button>
                <button
                  className="btn-secondary"
                  onClick={saveCurrentSession}
                  disabled={routerLensLoading}
                >
                  Save Session
                </button>
                <button
                  className="btn-secondary"
                  onClick={resetInspector}
                  disabled={routerLensLoading}
                >
                  Reset Inspector
                </button>
              </div>
            </div>

            {routerLensError && <div className="error-banner">{routerLensError}</div>}

            {routerStatus && (
              <div className="router-status-bar">
                <span className="status-indicator active">● Active</span>
                <span>Experts: {routerStatus.num_experts}</span>
                <span>Top-K: {routerStatus.top_k}</span>
                <span>Session Tokens: {routerStatus.current_session_tokens}</span>
              </div>
            )}

            <div className="router-lens-tabs">
              <button
                className={selectedSessionView === 'current' ? 'active' : ''}
                onClick={() => {
                  setSelectedSessionView('current');
                  fetchCurrentSession();
                }}
              >
                Current Session
              </button>
              <button
                className={selectedSessionView === 'saved' ? 'active' : ''}
                onClick={() => setSelectedSessionView('saved')}
              >
                Saved Sessions ({savedSessions.length})
              </button>
              <button
                className={selectedSessionView === 'analysis' ? 'active' : ''}
                onClick={() => setSelectedSessionView('analysis')}
              >
                Analysis
              </button>
            </div>

            {routerLensLoading && <div className="loading-indicator">Loading...</div>}

            {selectedSessionView === 'current' && currentSession && (
              <div className="current-session-view">
                <div className="session-stats-grid">
                  <div className="stat-card">
                    <div className="stat-value">{currentSession.total_tokens}</div>
                    <div className="stat-label">Total Tokens</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-value">{currentSession.unique_experts_used}</div>
                    <div className="stat-label">Unique Experts</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-value">{currentSession.usage_entropy.toFixed(3)}</div>
                    <div className="stat-label">Usage Entropy</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-value">{currentSession.mean_token_entropy.toFixed(3)}</div>
                    <div className="stat-label">Mean Token Entropy</div>
                  </div>
                </div>

                <div className="expert-usage-section">
                  <h5>Top Expert Activations</h5>
                  <div className="expert-bars">
                    {currentSession.top_experts.slice(0, 10).map((expert) => (
                      <div key={expert.expert_id} className="expert-bar-row">
                        <span className="expert-id">E{expert.expert_id}</span>
                        <div className="expert-bar-container">
                          <div
                            className="expert-bar-fill"
                            style={{ width: `${expert.percentage}%` }}
                          />
                        </div>
                        <span className="expert-count">{expert.count}</span>
                        <span className="expert-pct">{expert.percentage.toFixed(1)}%</span>
                      </div>
                    ))}
                  </div>
                </div>

                {currentSession.co_occurrence_top_pairs.length > 0 && (
                  <div className="co-occurrence-section">
                    <h5>Top Expert Co-occurrences</h5>
                    <div className="co-occurrence-list">
                      {currentSession.co_occurrence_top_pairs.slice(0, 8).map(([[e1, e2], count], idx) => (
                        <div key={idx} className="co-occurrence-item">
                          <span className="expert-pair">
                            E{e1} ↔ E{e2}
                          </span>
                          <span className="occurrence-count">{count} times</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {selectedSessionView === 'current' && !currentSession && !routerLensLoading && (
              <div className="empty-session">
                <p>No session data yet. Run inference with Router Lens enabled to capture expert activations.</p>
                <button className="btn-primary" onClick={fetchCurrentSession}>
                  Load Current Session
                </button>
              </div>
            )}

            {selectedSessionView === 'saved' && (
              <div className="saved-sessions-view">
                {savedSessions.length === 0 ? (
                  <div className="empty-sessions">
                    <p>No saved sessions yet. Save sessions during inference to analyze patterns over time.</p>
                  </div>
                ) : (
                  <div className="sessions-list">
                    {savedSessions.map((session) => (
                      <div key={session.filename} className="session-item">
                        <div className="session-time">
                          {new Date(session.start_time).toLocaleString()}
                        </div>
                        <div className="session-meta">
                          <span>{session.total_tokens} tokens</span>
                          {session.prompt_preview && (
                            <span className="prompt-preview">"{session.prompt_preview}..."</span>
                          )}
                        </div>
                        <button
                          className="btn-sm"
                          onClick={() => alert(`TODO: Load session ${session.filename}`)}
                        >
                          View Details
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {selectedSessionView === 'analysis' && (
              <div className="analysis-view">
                <div className="analysis-actions">
                  <button
                    className="btn-primary"
                    onClick={analyzeExpertUsage}
                    disabled={routerLensLoading}
                  >
                    Analyze Expert Usage
                  </button>
                  <button
                    className="btn-primary"
                    onClick={analyzeEntropy}
                    disabled={routerLensLoading}
                  >
                    Analyze Entropy
                  </button>
                </div>

                {expertAnalysis && (
                  <div className="analysis-results">
                    <h5>Expert Usage Analysis ({expertAnalysis.num_sessions_analyzed} sessions)</h5>
                    <div className="analysis-grid">
                      <div className="analysis-card">
                        <h6>Most Used Experts</h6>
                        <div className="expert-list">
                          {expertAnalysis.most_used.slice(0, 10).map(([expertId, count]) => (
                            <div key={expertId} className="expert-item">
                              <span className="expert-id">Expert {expertId}</span>
                              <span className="usage-count">{count} activations</span>
                            </div>
                          ))}
                        </div>
                      </div>
                      <div className="analysis-card">
                        <h6>Least Used Experts</h6>
                        <div className="expert-list">
                          {expertAnalysis.least_used.slice(0, 10).map(([expertId, count]) => (
                            <div key={expertId} className="expert-item">
                              <span className="expert-id">Expert {expertId}</span>
                              <span className="usage-count">{count} activations</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                    {expertAnalysis.expert_clusters.length > 0 && (
                      <div className="clusters-section">
                        <h6>Expert Clusters (Co-activation Patterns)</h6>
                        <div className="clusters-list">
                          {expertAnalysis.expert_clusters.map((cluster, idx) => (
                            <div key={idx} className="cluster-item">
                              <span className="cluster-label">Cluster {idx + 1}:</span>
                              <span className="cluster-experts">
                                {cluster.map((e) => `E${e}`).join(', ')}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {entropyAnalysis && (
                  <div className="entropy-results">
                    <h5>Entropy Distribution Analysis</h5>
                    <div className="entropy-stats">
                      <div className="stat-card">
                        <div className="stat-value">
                          {entropyAnalysis.overall_mean_entropy.toFixed(4)}
                        </div>
                        <div className="stat-label">Mean Entropy</div>
                      </div>
                      <div className="stat-card">
                        <div className="stat-value">
                          {entropyAnalysis.overall_std_entropy.toFixed(4)}
                        </div>
                        <div className="stat-label">Std Entropy</div>
                      </div>
                    </div>

                    <div className="entropy-histogram">
                      <h6>Entropy Distribution</h6>
                      <div className="histogram-bars">
                        {entropyAnalysis.entropy_histogram.map((count, idx) => {
                          const maxCount = Math.max(...entropyAnalysis.entropy_histogram);
                          const heightPct = maxCount > 0 ? (count / maxCount) * 100 : 0;
                          return (
                            <div key={idx} className="histogram-bar-wrapper">
                              <div
                                className="histogram-bar"
                                style={{ height: `${heightPct}%` }}
                                title={`${entropyAnalysis.entropy_bin_edges[idx].toFixed(2)} - ${entropyAnalysis.entropy_bin_edges[idx + 1].toFixed(2)}: ${count} tokens`}
                              />
                            </div>
                          );
                        })}
                      </div>
                      <div className="histogram-labels">
                        <span>Low Entropy</span>
                        <span>High Entropy</span>
                      </div>
                    </div>

                    <div className="per-session-entropy">
                      <h6>Per-Session Entropy</h6>
                      <div className="session-entropy-list">
                        {entropyAnalysis.per_session.slice(0, 10).map((sess) => (
                          <div key={sess.filename} className="session-entropy-item">
                            <span className="session-name">{sess.filename}</span>
                            <span className="entropy-range">
                              {sess.min_entropy.toFixed(3)} - {sess.max_entropy.toFixed(3)}
                            </span>
                            <span className="entropy-mean">μ={sess.mean_entropy.toFixed(3)}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}

                {!expertAnalysis && !entropyAnalysis && (
                  <div className="empty-analysis">
                    <p>
                      Run analysis on saved sessions to discover expert specialization patterns and router
                      behavior characteristics.
                    </p>
                  </div>
                )}
              </div>
            )}

            <div className="diagnostic-prompts-section">
              <h5>Diagnostic Prompts</h5>
              <p>Use these prompts to test expert routing for different cognitive tasks:</p>
              <div className="diagnostic-prompts-list">
                {diagnosticPrompts.map((dp, idx) => (
                  <div key={idx} className="diagnostic-prompt-item">
                    <span className="prompt-category">{dp.category}</span>
                    <span className="prompt-text">{dp.prompt}</span>
                    <button
                      className="btn-sm"
                      onClick={() => alert(`TODO: Run diagnostic with prompt: ${dp.prompt}`)}
                    >
                      Test
                    </button>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {showNewJobModal && (
        <div className="modal-overlay" onClick={() => setShowNewJobModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>New Training Job</h3>
            <p>TODO: Full training configuration form</p>
            <ul>
              <li>Base model selection</li>
              <li>Dataset selection</li>
              <li>Training type (LoRA/QLoRA/Full)</li>
              <li>MoE-specific options:
                <ul>
                  <li>Target expert selection</li>
                  <li>Router training toggle</li>
                  <li>Balance loss configuration</li>
                  <li>Expert masking schedule</li>
                </ul>
              </li>
              <li>Tag token configuration</li>
              <li>Curriculum phases</li>
              <li>DPO/preference stage setup</li>
            </ul>
            <button onClick={() => setShowNewJobModal(false)}>Close</button>
          </div>
        </div>
      )}
    </div>
  );
}

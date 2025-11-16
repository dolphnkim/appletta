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

  // Model loader state
  const [modelPath, setModelPath] = useState<string>('');
  const [adapterPath, setAdapterPath] = useState<string>('');
  const [modelStatus, setModelStatus] = useState<{ loaded: boolean; path: string | null; isMoE: boolean } | null>(
    null
  );

  // New job form state
  const [newJobConfig, setNewJobConfig] = useState<TrainingConfig>({
    base_model: '',
    dataset_id: '',
    training_type: 'lora',
    lora_rank: 16,
    lora_alpha: 32,
    learning_rate: 1e-4,
    epochs: 10,
    batch_size: 4,
    moe_enabled: false,
    target_experts: [],
    train_router: false,
    router_lr: 1e-6,
    expert_balance_lambda: 0.01,
  });
  const [newJobName, setNewJobName] = useState<string>('');
  const [targetExpertsInput, setTargetExpertsInput] = useState<string>('');

  // Fetch Router Lens status when MoE Debug tab is active
  useEffect(() => {
    if (activeSection === 'moe-debug') {
      fetchRouterLensStatus();
      fetchDiagnosticPrompts();
      fetchSavedSessions();
      fetchModelStatus();
    }
  }, [activeSection]);

  const fetchModelStatus = async () => {
    try {
      const status = await routerLensAPI.getDiagnosticModelStatus();
      setModelStatus({
        loaded: status.model_loaded,
        path: status.model_path,
        isMoE: status.is_moe_model,
      });
    } catch {
      // MLX might not be installed - that's okay, we'll show the error when they try to load
      setModelStatus(null);
    }
  };

  const loadModel = async () => {
    if (!modelPath.trim()) {
      setRouterLensError('Please enter a model path');
      return;
    }

    try {
      setRouterLensLoading(true);
      setRouterLensError(null);
      const result = await routerLensAPI.loadDiagnosticModel(
        modelPath.trim(),
        adapterPath.trim() || undefined
      );
      setModelStatus({
        loaded: true,
        path: result.model_path,
        isMoE: result.is_moe,
      });
      alert(
        `Model loaded successfully!\n\nPath: ${result.model_path}\nMoE Model: ${result.is_moe ? 'Yes' : 'No'}\n\n${result.is_moe ? 'Router introspection enabled.' : 'Warning: Not an MoE model, router logging disabled.'}`
      );
    } catch (err: unknown) {
      console.error('Failed to load model:', err);
      const error = err as { message?: string };
      if (error.message?.includes('MLX not installed')) {
        setRouterLensError('MLX is not installed. Please install: pip install mlx mlx-lm');
      } else if (error.message?.includes('404')) {
        setRouterLensError('Model not found at the specified path');
      } else {
        setRouterLensError(`Failed to load model: ${error.message || 'Unknown error'}`);
      }
    } finally {
      setRouterLensLoading(false);
    }
  };

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

  const runQuickTest = async () => {
    try {
      setRouterLensLoading(true);
      setRouterLensError(null);
      const result = await routerLensAPI.runQuickTest();
      setCurrentSession(result.router_analysis);
      setSelectedSessionView('current');

      alert(`Quick Test Complete\n\nPrompt: ${result.prompt}\nResponse: ${result.response}`);
    } catch (err: unknown) {
      console.error('Failed to run quick test:', err);
      const error = err as { message?: string };
      if (error.message?.includes('No model loaded') || error.message?.includes('400')) {
        setRouterLensError(
          'No model loaded. Load an MoE model first using the model loader below.'
        );
      } else if (error.message?.includes('MLX not installed') || error.message?.includes('500')) {
        setRouterLensError(
          'MLX is not installed on the backend. Please install: pip install mlx mlx-lm'
        );
      } else {
        setRouterLensError('Failed to run quick test. Check backend logs.');
      }
    } finally {
      setRouterLensLoading(false);
    }
  };

  const resetNewJobForm = () => {
    setNewJobName('');
    setNewJobConfig({
      base_model: '',
      dataset_id: '',
      training_type: 'lora',
      lora_rank: 16,
      lora_alpha: 32,
      learning_rate: 1e-4,
      epochs: 10,
      batch_size: 4,
      moe_enabled: false,
      target_experts: [],
      train_router: false,
      router_lr: 1e-6,
      expert_balance_lambda: 0.01,
    });
    setTargetExpertsInput('');
  };

  const handleCreateJob = () => {
    if (!newJobName.trim()) {
      alert('Please enter a job name');
      return;
    }
    if (!newJobConfig.base_model) {
      alert('Please select a base model');
      return;
    }
    if (!newJobConfig.dataset_id) {
      alert('Please select a dataset');
      return;
    }

    // Parse target experts from comma-separated string
    const targetExperts = targetExpertsInput
      .split(',')
      .map((s) => parseInt(s.trim()))
      .filter((n) => !isNaN(n) && n >= 0);

    const newJob: TrainingJob = {
      id: Date.now().toString(),
      name: newJobName.trim(),
      status: 'pending',
      config: {
        ...newJobConfig,
        target_experts: targetExperts.length > 0 ? targetExperts : undefined,
      },
      created_at: new Date().toISOString(),
    };

    setJobs([newJob, ...jobs]);
    setShowNewJobModal(false);
    resetNewJobForm();
    alert(`Training job "${newJob.name}" created! (Note: Backend training not yet implemented)`);
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
                  className="btn-primary"
                  onClick={runQuickTest}
                  disabled={routerLensLoading}
                >
                  ⚡ Quick Test
                </button>
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

            {/* Model Loader Section */}
            <div className="model-loader-section">
              <h5>Model Status</h5>
              {modelStatus?.loaded ? (
                <div className="model-loaded-info">
                  <span className="status-indicator active">● Model Loaded</span>
                  <span className="model-path">{modelStatus.path}</span>
                  <span className={`moe-badge ${modelStatus.isMoE ? 'is-moe' : 'not-moe'}`}>
                    {modelStatus.isMoE ? '🔀 MoE Model' : '⚠️ Not MoE'}
                  </span>
                </div>
              ) : (
                <div className="model-loader-form">
                  <div className="form-row">
                    <label>Model Path:</label>
                    <input
                      type="text"
                      value={modelPath}
                      onChange={(e) => setModelPath(e.target.value)}
                      placeholder="e.g., ~/.cache/huggingface/Qwen2-MoE-3B"
                    />
                  </div>
                  <div className="form-row">
                    <label>Adapter Path (optional):</label>
                    <input
                      type="text"
                      value={adapterPath}
                      onChange={(e) => setAdapterPath(e.target.value)}
                      placeholder="e.g., ./adapters/my-lora"
                    />
                  </div>
                  <button
                    className="btn-primary"
                    onClick={loadModel}
                    disabled={routerLensLoading || !modelPath.trim()}
                  >
                    Load Model for Diagnostics
                  </button>
                </div>
              )}
            </div>

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
                <p>No session data yet. Run a quick test to capture expert activations.</p>
                <button className="btn-primary" onClick={runQuickTest} disabled={routerLensLoading}>
                  ⚡ Run Quick Test
                </button>
                <button className="btn-secondary" onClick={fetchCurrentSession} style={{ marginLeft: '10px' }}>
                  Load Existing Session
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
          <div className="modal-content new-job-modal" onClick={(e) => e.stopPropagation()}>
            <h3>New Training Job</h3>

            <div className="job-form">
              {/* Basic Info */}
              <div className="form-section">
                <h4>Basic Configuration</h4>
                <div className="form-row">
                  <label>Job Name:</label>
                  <input
                    type="text"
                    value={newJobName}
                    onChange={(e) => setNewJobName(e.target.value)}
                    placeholder="e.g., Persona LoRA v2"
                  />
                </div>

                <div className="form-row">
                  <label>Base Model:</label>
                  <select
                    value={newJobConfig.base_model}
                    onChange={(e) => setNewJobConfig({ ...newJobConfig, base_model: e.target.value })}
                  >
                    <option value="">Select a model...</option>
                    <option value="Qwen2-MoE-3B">Qwen2-MoE-3B</option>
                    <option value="Qwen2-MoE-7B">Qwen2-MoE-7B</option>
                    <option value="Mixtral-8x7B">Mixtral-8x7B</option>
                    <option value="custom">Custom Path...</option>
                  </select>
                </div>

                <div className="form-row">
                  <label>Dataset:</label>
                  <select
                    value={newJobConfig.dataset_id}
                    onChange={(e) => setNewJobConfig({ ...newJobConfig, dataset_id: e.target.value })}
                  >
                    <option value="">Select a dataset...</option>
                    {datasets.map((ds) => (
                      <option key={ds.id} value={ds.id}>
                        {ds.name} ({ds.num_examples} examples)
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Training Type */}
              <div className="form-section">
                <h4>Training Method</h4>
                <div className="form-row">
                  <label>Training Type:</label>
                  <div className="radio-group">
                    <label className="radio-label">
                      <input
                        type="radio"
                        name="training_type"
                        value="lora"
                        checked={newJobConfig.training_type === 'lora'}
                        onChange={(e) =>
                          setNewJobConfig({
                            ...newJobConfig,
                            training_type: e.target.value as 'lora' | 'qlora' | 'full',
                          })
                        }
                      />
                      LoRA
                    </label>
                    <label className="radio-label">
                      <input
                        type="radio"
                        name="training_type"
                        value="qlora"
                        checked={newJobConfig.training_type === 'qlora'}
                        onChange={(e) =>
                          setNewJobConfig({
                            ...newJobConfig,
                            training_type: e.target.value as 'lora' | 'qlora' | 'full',
                          })
                        }
                      />
                      QLoRA (4-bit)
                    </label>
                    <label className="radio-label">
                      <input
                        type="radio"
                        name="training_type"
                        value="full"
                        checked={newJobConfig.training_type === 'full'}
                        onChange={(e) =>
                          setNewJobConfig({
                            ...newJobConfig,
                            training_type: e.target.value as 'lora' | 'qlora' | 'full',
                          })
                        }
                      />
                      Full Fine-tune
                    </label>
                  </div>
                </div>

                {newJobConfig.training_type !== 'full' && (
                  <div className="lora-params">
                    <div className="form-row inline">
                      <label>LoRA Rank (r):</label>
                      <input
                        type="number"
                        min="4"
                        max="128"
                        value={newJobConfig.lora_rank}
                        onChange={(e) => setNewJobConfig({ ...newJobConfig, lora_rank: parseInt(e.target.value) })}
                      />
                    </div>
                    <div className="form-row inline">
                      <label>LoRA Alpha:</label>
                      <input
                        type="number"
                        min="8"
                        max="256"
                        value={newJobConfig.lora_alpha}
                        onChange={(e) => setNewJobConfig({ ...newJobConfig, lora_alpha: parseInt(e.target.value) })}
                      />
                    </div>
                  </div>
                )}
              </div>

              {/* Hyperparameters */}
              <div className="form-section">
                <h4>Hyperparameters</h4>
                <div className="hyperparam-grid">
                  <div className="form-row inline">
                    <label>Learning Rate:</label>
                    <input
                      type="number"
                      step="0.00001"
                      min="0.000001"
                      max="0.01"
                      value={newJobConfig.learning_rate}
                      onChange={(e) => setNewJobConfig({ ...newJobConfig, learning_rate: parseFloat(e.target.value) })}
                    />
                  </div>
                  <div className="form-row inline">
                    <label>Epochs:</label>
                    <input
                      type="number"
                      min="1"
                      max="100"
                      value={newJobConfig.epochs}
                      onChange={(e) => setNewJobConfig({ ...newJobConfig, epochs: parseInt(e.target.value) })}
                    />
                  </div>
                  <div className="form-row inline">
                    <label>Batch Size:</label>
                    <input
                      type="number"
                      min="1"
                      max="32"
                      value={newJobConfig.batch_size}
                      onChange={(e) => setNewJobConfig({ ...newJobConfig, batch_size: parseInt(e.target.value) })}
                    />
                  </div>
                </div>
              </div>

              {/* MoE Options */}
              <div className="form-section moe-section">
                <h4>
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={newJobConfig.moe_enabled}
                      onChange={(e) => setNewJobConfig({ ...newJobConfig, moe_enabled: e.target.checked })}
                    />
                    MoE-Specific Options
                  </label>
                </h4>

                {newJobConfig.moe_enabled && (
                  <div className="moe-options">
                    <div className="form-row">
                      <label>Target Experts (comma-separated IDs, leave empty for all):</label>
                      <input
                        type="text"
                        value={targetExpertsInput}
                        onChange={(e) => setTargetExpertsInput(e.target.value)}
                        placeholder="e.g., 2, 7, 14, 23"
                      />
                      <small>Specify which experts to train. Empty = train all experts.</small>
                    </div>

                    <div className="form-row">
                      <label className="checkbox-label">
                        <input
                          type="checkbox"
                          checked={newJobConfig.train_router}
                          onChange={(e) => setNewJobConfig({ ...newJobConfig, train_router: e.target.checked })}
                        />
                        Train Router (gate) weights
                      </label>
                    </div>

                    {newJobConfig.train_router && (
                      <div className="form-row inline">
                        <label>Router Learning Rate:</label>
                        <input
                          type="number"
                          step="0.0000001"
                          min="0.0000001"
                          max="0.001"
                          value={newJobConfig.router_lr}
                          onChange={(e) => setNewJobConfig({ ...newJobConfig, router_lr: parseFloat(e.target.value) })}
                        />
                      </div>
                    )}

                    <div className="form-row inline">
                      <label>Expert Balance Lambda:</label>
                      <input
                        type="number"
                        step="0.001"
                        min="0"
                        max="1"
                        value={newJobConfig.expert_balance_lambda}
                        onChange={(e) =>
                          setNewJobConfig({ ...newJobConfig, expert_balance_lambda: parseFloat(e.target.value) })
                        }
                      />
                      <small>Loss penalty for uneven expert usage (0 = disabled)</small>
                    </div>
                  </div>
                )}
              </div>
            </div>

            <div className="modal-actions">
              <button
                className="btn-secondary"
                onClick={() => {
                  setShowNewJobModal(false);
                  resetNewJobForm();
                }}
              >
                Cancel
              </button>
              <button className="btn-primary" onClick={handleCreateJob}>
                Create Job
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

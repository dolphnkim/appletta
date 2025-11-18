import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import AffectDashboard from '../components/AffectDashboard/AffectDashboard';
import { routerLensAPI } from '../api/routerLensAPI';
import { conversationAPI } from '../api/conversationAPI';
import { agentAPI } from '../api/agentAPI';
import type {
  RouterLensStatus,
  SessionSummary,
  SavedSession,
  ExpertUsageAnalysis,
  EntropyAnalysis,
  DiagnosticPrompt,
} from '../api/routerLensAPI';
import type { Conversation } from '../types/conversation';
import type { Agent } from '../types/agent';
import './InterpretabilityView.css';

export default function InterpretabilityView() {
  const navigate = useNavigate();
  const agentId = localStorage.getItem('selectedAgentId') || '';
  const [activeTab, setActiveTab] = useState<'expert' | 'welfare'>('expert');

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

  // Agent selection state
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedAgentForExpert, setSelectedAgentForExpert] = useState<string>('');
  const [modelStatus, setModelStatus] = useState<{
    loaded: boolean;
    path: string | null;
    isMoE: boolean;
    agentId: string | null;
    agentName: string | null;
  } | null>(null);

  // Welfare tracking state
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);
  const [conversationsLoading, setConversationsLoading] = useState(false);

  // Diagnostic test state
  const [diagnosticTestResult, setDiagnosticTestResult] = useState<{
    prompt: string;
    response: string;
    category: string;
    router_analysis: SessionSummary;
  } | null>(null);
  const [showDiagnosticResult, setShowDiagnosticResult] = useState(false);

  // Fetch agents on mount
  useEffect(() => {
    fetchAgents();
  }, []);

  // Fetch data when Expert Analytics tab is active
  useEffect(() => {
    if (activeTab === 'expert') {
      fetchRouterLensStatus();
      fetchDiagnosticPrompts();
      fetchModelStatus();
    }
  }, [activeTab]);

  // Fetch sessions when agent changes
  useEffect(() => {
    if (selectedAgentForExpert) {
      fetchSavedSessions();
    }
  }, [selectedAgentForExpert]);

  // Fetch conversations when Welfare tab is active or agent changes
  useEffect(() => {
    if (activeTab === 'welfare' && agentId) {
      fetchConversations();
    }
  }, [activeTab, agentId]);

  const fetchAgents = async () => {
    try {
      const fetchedAgents = await agentAPI.list();
      setAgents(fetchedAgents);

      // Auto-select the locally stored agent or first agent
      if (agentId && fetchedAgents.some((a) => a.id === agentId)) {
        setSelectedAgentForExpert(agentId);
      } else if (fetchedAgents.length > 0) {
        setSelectedAgentForExpert(fetchedAgents[0].id);
      }
    } catch (err) {
      console.error('Failed to fetch agents:', err);
    }
  };

  const fetchModelStatus = async () => {
    try {
      const status = await routerLensAPI.getDiagnosticModelStatus();
      setModelStatus({
        loaded: status.model_loaded,
        path: status.model_path,
        isMoE: status.is_moe_model,
        agentId: status.agent_id,
        agentName: status.agent_name,
      });
      // If an agent is already loaded, select it
      if (status.agent_id && !selectedAgentForExpert) {
        setSelectedAgentForExpert(status.agent_id);
      }
    } catch {
      setModelStatus(null);
    }
  };

  const loadAgentModel = async () => {
    if (!selectedAgentForExpert) {
      setRouterLensError('Please select an agent');
      return;
    }

    try {
      setRouterLensLoading(true);
      setRouterLensError(null);
      const result = await routerLensAPI.loadAgentModel(selectedAgentForExpert);
      setModelStatus({
        loaded: true,
        path: result.model_path,
        isMoE: result.is_moe,
        agentId: result.agent_id,
        agentName: result.agent_name,
      });
      // Reload sessions for this agent
      fetchSavedSessions();
    } catch (err: unknown) {
      console.error('Failed to load agent model:', err);
      const error = err as { message?: string };
      if (error.message?.includes('MLX not installed')) {
        setRouterLensError('MLX is not installed. Please install: pip install mlx mlx-lm');
      } else if (error.message?.includes('404')) {
        setRouterLensError('Agent or model not found');
      } else {
        setRouterLensError(`Failed to load agent model: ${error.message || 'Unknown error'}`);
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
      // Pass agent ID if one is selected to get agent-specific sessions
      const result = await routerLensAPI.listSessions(20, selectedAgentForExpert || undefined);
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

  const fetchConversations = async () => {
    if (!agentId) return;

    try {
      setConversationsLoading(true);
      const convos = await conversationAPI.list(agentId);
      setConversations(convos);

      // Auto-select the most recent conversation if none selected
      if (convos.length > 0 && !selectedConversationId) {
        // Sort by updated_at to get the most recent
        const sorted = [...convos].sort((a, b) =>
          new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
        );
        setSelectedConversationId(sorted[0].id);
      }
    } catch (err) {
      console.error('Failed to fetch conversations:', err);
    } finally {
      setConversationsLoading(false);
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

  const saveDiagnosticTestSession = async () => {
    if (!diagnosticTestResult) return;

    try {
      setRouterLensLoading(true);
      const promptPreview = `[${diagnosticTestResult.category}] ${diagnosticTestResult.prompt}`;
      await routerLensAPI.saveDiagnosticSession(promptPreview, '');
      await fetchSavedSessions();
      setShowDiagnosticResult(false);
      alert('Diagnostic session saved successfully!');
    } catch (err) {
      console.error('Failed to save diagnostic session:', err);
      alert('Failed to save diagnostic session');
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

  const runDiagnosticTest = async (prompt: string, category: string) => {
    try {
      setRouterLensLoading(true);
      setRouterLensError(null);
      const result = await routerLensAPI.runDiagnosticInference(prompt, 100, 0.7);

      // Update current session with the diagnostic results
      setCurrentSession(result.router_analysis);
      setSelectedSessionView('current');

      // Store the diagnostic result for display
      setDiagnosticTestResult({
        prompt,
        response: result.response,
        category,
        router_analysis: result.router_analysis,
      });
      setShowDiagnosticResult(true);
    } catch (err: unknown) {
      console.error('Failed to run diagnostic test:', err);
      const error = err as { message?: string };
      if (error.message?.includes('No model loaded') || error.message?.includes('400')) {
        setRouterLensError(
          'No model loaded. Load an MoE model first using the model loader above.'
        );
      } else if (error.message?.includes('MLX not installed') || error.message?.includes('500')) {
        setRouterLensError(
          'MLX is not installed on the backend. Please install: pip install mlx mlx-lm'
        );
      } else {
        setRouterLensError(`Failed to run diagnostic test: ${error.message || 'Unknown error'}`);
      }
    } finally {
      setRouterLensLoading(false);
    }
  };

  return (
    <div className="interpretability-view">
      <header className="interpretability-view-header">
        <button className="back-button" onClick={() => navigate('/')}>
          ← Back to Dashboard
        </button>
        <h2>🔬 Interpretability</h2>
      </header>

      <div className="interpretability-tabs">
        <button
          className={activeTab === 'expert' ? 'active' : ''}
          onClick={() => setActiveTab('expert')}
        >
          MoE Expert Analytics
        </button>
        <button
          className={activeTab === 'welfare' ? 'active' : ''}
          onClick={() => setActiveTab('welfare')}
        >
          Welfare Tracking
        </button>
      </div>

      <div className="interpretability-view-content">
        {activeTab === 'expert' && (
          <div className="expert-analytics-section">
            <div className="section-header">
              <h3>🔬 Router Lens - Expert Activation Analytics</h3>
              <div className="router-lens-controls">
                <button
                  className="btn-primary"
                  onClick={runQuickTest}
                  disabled={routerLensLoading}
                >
                  Quick Test
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

            {/* Agent Selection Section */}
            <div className="model-loader-section">
              <h4>Agent Selection</h4>
              <div className="agent-selector-row">
                <label>Select Agent:</label>
                {agents.length === 0 ? (
                  <span className="no-agents">No agents found</span>
                ) : (
                  <select
                    value={selectedAgentForExpert}
                    onChange={(e) => setSelectedAgentForExpert(e.target.value)}
                    className="agent-select"
                  >
                    {agents.map((agent) => (
                      <option key={agent.id} value={agent.id}>
                        {agent.name}
                      </option>
                    ))}
                  </select>
                )}
              </div>

              {modelStatus?.loaded && modelStatus?.agentId === selectedAgentForExpert ? (
                <div className="model-loaded-info">
                  <span className="status-indicator active">● Model Loaded</span>
                  <span className="agent-name">{modelStatus.agentName}</span>
                  <span className="model-path">{modelStatus.path}</span>
                  <span className={`moe-badge ${modelStatus.isMoE ? 'is-moe' : 'not-moe'}`}>
                    {modelStatus.isMoE ? 'MoE Model' : 'Not MoE'}
                  </span>
                </div>
              ) : (
                <button
                  className="btn-primary"
                  onClick={loadAgentModel}
                  disabled={routerLensLoading || !selectedAgentForExpert}
                  style={{ marginTop: '12px' }}
                >
                  Load Agent Model for Analytics
                </button>
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

            {selectedSessionView === 'current' && currentSession && !('error' in currentSession) && (
              <div className="current-session-view">
                <div className="session-stats-grid">
                  <div className="stat-card">
                    <div className="stat-value">{currentSession.total_tokens || 0}</div>
                    <div className="stat-label" title="Total number of layer activations logged (layers × tokens)">
                      Layer Activations
                    </div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-value">
                      {(currentSession as any).actual_tokens_generated || 0}
                    </div>
                    <div className="stat-label" title="Actual tokens generated in the response">
                      Generated Tokens
                    </div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-value">{currentSession.unique_experts_used || 0}</div>
                    <div className="stat-label">Unique Experts</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-value">{(currentSession.usage_entropy || 0).toFixed(3)}</div>
                    <div className="stat-label" title="Higher values = more balanced expert usage">
                      Usage Entropy
                    </div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-value">{(currentSession.mean_token_entropy || 0).toFixed(3)}</div>
                    <div className="stat-label" title="Average entropy of router decisions per token">
                      Mean Token Entropy
                    </div>
                  </div>
                </div>

                <div className="expert-usage-section">
                  <h5>Top Expert Activations</h5>
                  <div className="expert-bars">
                    {(currentSession.top_experts || []).slice(0, 10).map((expert) => (
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

                {(currentSession.co_occurrence_top_pairs || []).length > 0 && (
                  <div className="co-occurrence-section">
                    <h5>Top Expert Co-occurrences</h5>
                    <div className="co-occurrence-list">
                      {(currentSession.co_occurrence_top_pairs || []).slice(0, 8).map(([[e1, e2], count], idx) => (
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

            {selectedSessionView === 'current' && currentSession && 'error' in currentSession && (
              <div className="empty-session">
                <p>No router data captured. Router introspection may have failed during inference.</p>
                <p className="error-detail">{(currentSession as { error: string }).error}</p>
              </div>
            )}

            {selectedSessionView === 'current' && !currentSession && !routerLensLoading && (
              <div className="empty-session">
                <p>No session data yet. Run a quick test to capture expert activations.</p>
                <button className="btn-primary" onClick={runQuickTest} disabled={routerLensLoading}>
                  Run Quick Test
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
                      onClick={() => runDiagnosticTest(dp.prompt, dp.category)}
                      disabled={routerLensLoading}
                    >
                      Test
                    </button>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'welfare' && (
          <div className="welfare-section">
            <div className="welfare-header">
              <h3>Welfare Tracking</h3>
              <div className="conversation-selector">
                <label>Select Conversation:</label>
                {conversationsLoading ? (
                  <span className="loading-text">Loading conversations...</span>
                ) : conversations.length === 0 ? (
                  <span className="no-conversations">No conversations found for this agent</span>
                ) : (
                  <select
                    value={selectedConversationId || ''}
                    onChange={(e) => setSelectedConversationId(e.target.value)}
                    className="conversation-select"
                  >
                    {conversations.map((convo) => (
                      <option key={convo.id} value={convo.id}>
                        {convo.title || `Conversation ${new Date(convo.created_at).toLocaleDateString()}`}
                      </option>
                    ))}
                  </select>
                )}
              </div>
            </div>
            <AffectDashboard conversationId={selectedConversationId || undefined} agentId={agentId} />
          </div>
        )}
      </div>

      {/* Diagnostic Test Result Modal */}
      {showDiagnosticResult && diagnosticTestResult && (
        <div className="modal-overlay" onClick={() => setShowDiagnosticResult(false)}>
          <div className="diagnostic-result-modal" onClick={(e) => e.stopPropagation()}>
            <div className="diagnostic-result-header">
              <h3>Diagnostic Test Results: {diagnosticTestResult.category}</h3>
              <button className="close-btn" onClick={() => setShowDiagnosticResult(false)}>
                ×
              </button>
            </div>

            <div className="diagnostic-result-content">
              <div className="diagnostic-result-section">
                <h4>Prompt</h4>
                <div className="diagnostic-prompt-display">{diagnosticTestResult.prompt}</div>
              </div>

              <div className="diagnostic-result-section">
                <h4>Model Response</h4>
                <div className="diagnostic-response-display">{diagnosticTestResult.response}</div>
              </div>

              <div className="diagnostic-result-section">
                <h4>Expert Routing Analysis</h4>
                <div className="diagnostic-stats-grid">
                  <div className="diagnostic-stat">
                    <span className="stat-label">Layer Activations</span>
                    <span className="stat-value">{diagnosticTestResult.router_analysis.total_tokens || 0}</span>
                  </div>
                  <div className="diagnostic-stat">
                    <span className="stat-label">Unique Experts Used</span>
                    <span className="stat-value">{diagnosticTestResult.router_analysis.unique_experts_used || 0}</span>
                  </div>
                  <div className="diagnostic-stat">
                    <span className="stat-label">Usage Entropy</span>
                    <span className="stat-value">{(diagnosticTestResult.router_analysis.usage_entropy || 0).toFixed(3)}</span>
                  </div>
                  <div className="diagnostic-stat">
                    <span className="stat-label">Mean Token Entropy</span>
                    <span className="stat-value">{(diagnosticTestResult.router_analysis.mean_token_entropy || 0).toFixed(3)}</span>
                  </div>
                </div>

                <div className="diagnostic-top-experts">
                  <h5>Top Activated Experts</h5>
                  <div className="expert-bars">
                    {diagnosticTestResult.router_analysis.top_experts.slice(0, 8).map((expert) => (
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
              </div>
            </div>

            <div className="diagnostic-result-footer">
              <button className="btn-secondary" onClick={() => setShowDiagnosticResult(false)}>
                Close
              </button>
              <button
                className="btn-primary"
                onClick={saveDiagnosticTestSession}
                disabled={routerLensLoading}
              >
                Save Session
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

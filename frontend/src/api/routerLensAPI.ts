/**
 * Router Lens API - MoE Introspection
 *
 * Provides access to router inspection data for understanding
 * expert behavior and activation patterns.
 */

const API_BASE = '/api/v1/router-lens';

async function fetchAPI(path: string, options?: RequestInit) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || 'API request failed');
  }

  return response.json();
}

export interface RouterLensStatus {
  status: string;
  num_experts: number;
  top_k: number;
  current_session_tokens: number;
  log_directory: string;
}

export interface SessionSummary {
  total_tokens: number;
  total_expert_activations: number;
  unique_experts_used: number;
  top_experts: Array<{ expert_id: number; count: number; percentage: number }>;
  usage_entropy: number;
  mean_token_entropy: number;
  expert_usage_distribution: Record<string, number>;
  co_occurrence_top_pairs: Array<[[number, number], number]>;
  start_time: string;
}

export interface SavedSession {
  filename: string;
  filepath: string;
  start_time: string;
  end_time?: string;
  total_tokens: number;
  prompt_preview: string;
}

export interface ExpertUsageAnalysis {
  aggregate_usage: Record<string, number>;
  expert_clusters: number[][];
  most_used: Array<[number, number]>;
  least_used: Array<[number, number]>;
  num_sessions_analyzed: number;
}

export interface EntropyAnalysis {
  overall_mean_entropy: number;
  overall_std_entropy: number;
  entropy_histogram: number[];
  entropy_bin_edges: number[];
  per_session: Array<{
    filename: string;
    mean_entropy: number;
    min_entropy: number;
    max_entropy: number;
  }>;
}

export interface DiagnosticPrompt {
  category: string;
  prompt: string;
}

export const routerLensAPI = {
  // Status
  getStatus: (): Promise<RouterLensStatus> => fetchAPI('/status'),

  resetInspector: (numExperts: number = 64, topK: number = 8): Promise<{ status: string; num_experts: number; top_k: number }> =>
    fetchAPI(`/reset?num_experts=${numExperts}&top_k=${topK}`, { method: 'POST' }),

  // Current session
  getSessionSummary: (): Promise<SessionSummary> => fetchAPI('/session/summary'),

  saveSession: (prompt: string = '', response: string = ''): Promise<{ saved: boolean; filepath: string }> =>
    fetchAPI(`/session/save?prompt=${encodeURIComponent(prompt)}&response=${encodeURIComponent(response)}`, { method: 'POST' }),

  // Saved sessions
  listSessions: (limit: number = 20, agentId?: string): Promise<{ sessions: SavedSession[]; total: number }> => {
    const params = new URLSearchParams({ limit: limit.toString() });
    if (agentId) {
      params.append('agent_id', agentId);
    }
    return fetchAPI(`/sessions?${params.toString()}`);
  },

  getSessionDetails: (filename: string): Promise<any> => fetchAPI(`/sessions/${filename}`),

  // Analysis
  analyzeExpertUsage: (): Promise<ExpertUsageAnalysis> =>
    fetchAPI('/analyze/expert-usage', { method: 'POST' }),

  analyzeEntropyDistribution: (): Promise<EntropyAnalysis> =>
    fetchAPI('/analyze/entropy-distribution', { method: 'POST' }),

  getExpertClusters: (): Promise<{ clusters: number[][]; most_used: Array<[number, number]>; least_used: Array<[number, number]> }> =>
    fetchAPI('/expert-clusters'),

  // Diagnostic prompts
  getDiagnosticPrompts: (): Promise<{ prompts: DiagnosticPrompt[] }> => fetchAPI('/diagnostic-prompts'),

  // Real-time monitoring
  getCurrentMonitoringData: (): Promise<any> => fetchAPI('/monitor/current'),

  // Expert masking simulation (placeholder)
  simulateExpertMask: (agentId: string, prompt: string, disabledExperts: number[]): Promise<any> =>
    fetchAPI('/simulate/expert-mask', {
      method: 'POST',
      body: JSON.stringify({
        agent_id: agentId,
        prompt: prompt,
        disabled_experts: disabledExperts,
      }),
    }),

  // Diagnostic inference - direct model loading with router logging
  loadDiagnosticModel: (
    modelPath: string,
    adapterPath?: string
  ): Promise<{
    status: string;
    model_path: string;
    is_moe: boolean;
    config: Record<string, unknown>;
  }> =>
    fetchAPI('/diagnostic/load-model', {
      method: 'POST',
      body: JSON.stringify({
        model_path: modelPath,
        adapter_path: adapterPath || null,
      }),
    }),

  // Load agent's model for diagnostics
  loadAgentModel: (
    agentId: string
  ): Promise<{
    status: string;
    model_path: string;
    is_moe: boolean;
    agent_id: string;
    agent_name: string;
    config: Record<string, unknown>;
  }> =>
    fetchAPI(`/diagnostic/load-agent-model/${agentId}`, {
      method: 'POST',
    }),

  runQuickTest: (): Promise<{
    prompt: string;
    response: string;
    router_analysis: SessionSummary;
    timestamp: string;
  }> => fetchAPI('/diagnostic/quick-test', { method: 'POST' }),

  runDiagnosticInference: (
    prompt: string,
    maxTokens: number = 100,
    temperature: number = 0.7
  ): Promise<{
    prompt: string;
    response: string;
    router_analysis: SessionSummary;
    timestamp: string;
  }> =>
    fetchAPI('/diagnostic/infer', {
      method: 'POST',
      body: JSON.stringify({
        prompt,
        max_tokens: maxTokens,
        temperature,
      }),
    }),

  getDiagnosticModelStatus: (): Promise<{
    model_loaded: boolean;
    model_path: string | null;
    is_moe_model: boolean;
    agent_id: string | null;
    agent_name: string | null;
    inspector_status: RouterLensStatus;
  }> => fetchAPI('/diagnostic/model-status'),

  saveDiagnosticSession: (promptPreview: string = '', notes: string = ''): Promise<{ saved: boolean; filepath: string }> =>
    fetchAPI(`/diagnostic/save-session?prompt_preview=${encodeURIComponent(promptPreview)}&notes=${encodeURIComponent(notes)}`, { method: 'POST' }),

  // Model browsing
  getConfigPaths: (): Promise<{
    models_dir: string;
    adapters_dir: string;
  }> => fetchAPI('/config/paths'),

  browseModels: (): Promise<{
    models: Array<{ name: string; path: string; type: string }>;
    base_path: string;
    exists: boolean;
  }> => fetchAPI('/browse/models'),

  browseAdapters: (): Promise<{
    adapters: Array<{ name: string; path: string }>;
    base_path: string;
    exists: boolean;
  }> => fetchAPI('/browse/adapters'),

  browseDirectory: (
    path: string = '~'
  ): Promise<{
    path: string;
    exists: boolean;
    items: Array<{
      name: string;
      path: string;
      is_dir: boolean;
      is_model?: boolean;
      is_adapter?: boolean;
    }>;
    parent: string | null;
  }> => fetchAPI(`/browse/directory?path=${encodeURIComponent(path)}`),
};

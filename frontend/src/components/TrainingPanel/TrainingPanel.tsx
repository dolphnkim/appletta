import { useState, useEffect } from 'react';
import './TrainingPanel.css';

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
              <button className="btn-primary" onClick={() => alert('TODO: Run diagnostic')}>
                Run Diagnostic
              </button>
            </div>

            <div className="debug-tools">
              <div className="debug-card">
                <h5>Expert Usage Histogram</h5>
                <p>Run inference on test prompts and visualize which experts are activated.</p>
                <button onClick={() => alert('TODO: Expert histogram modal')}>View Histogram</button>
              </div>

              <div className="debug-card">
                <h5>Router Logit Inspector</h5>
                <p>See raw router scores for each token during generation.</p>
                <button onClick={() => alert('TODO: Logit inspector')}>Open Inspector</button>
              </div>

              <div className="debug-card">
                <h5>Expert Masking Tester</h5>
                <p>Force-disable specific experts and see how responses change.</p>
                <button onClick={() => alert('TODO: Masking tester')}>Test Masking</button>
              </div>

              <div className="debug-card">
                <h5>Persona Consistency Score</h5>
                <p>Evaluate responses against persona embedding centroids.</p>
                <button onClick={() => alert('TODO: Consistency scorer')}>Calculate Score</button>
              </div>

              <div className="debug-card">
                <h5>Expert Role Discovery</h5>
                <p>Cluster expert activations to discover emergent specializations.</p>
                <button onClick={() => alert('TODO: Role discovery')}>Discover Roles</button>
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

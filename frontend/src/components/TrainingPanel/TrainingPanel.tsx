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
  const [activeSection, setActiveSection] = useState<'datasets' | 'jobs'>('datasets');
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [jobs, setJobs] = useState<TrainingJob[]>([]);
  const [showNewJobModal, setShowNewJobModal] = useState(false);

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
        <h3>Training Lab</h3>
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
                        <div>MoE Mode</div>
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

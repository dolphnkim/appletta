import { useState } from 'react';
import { useAgent } from '../../hooks/useAgent';
import AgentHeader from './AgentHeader';
import EditableField from './EditableField';
import SystemInstructionsModal from './SystemInstructionsModal';
import AgentManagement from './AgentManagement';
import LLMConfig from './LLMConfig';
import EmbeddingConfig from './EmbeddingConfig';
import './AgentSettings.css';

interface AgentSettingsProps {
  agentId: string;
  onDelete?: () => void;
  onClone?: (newAgentId: string) => void;
}

export default function AgentSettings({ agentId, onDelete, onClone }: AgentSettingsProps) {
  const { agent, loading, error, updateAgent, cloneAgent, deleteAgent, exportAgent } = useAgent(agentId);
  const [showSystemInstructionsModal, setShowSystemInstructionsModal] = useState(false);

  if (loading) {
    return <div className="agent-settings loading">Loading agent...</div>;
  }

  if (error || !agent) {
    return <div className="agent-settings error">{error || 'Agent not found'}</div>;
  }

  const handleNameUpdate = async (name: string) => {
    await updateAgent({ name });
  };

  const handleDescriptionUpdate = async (description: string) => {
    await updateAgent({ description });
  };

  const handleModelPathUpdate = async (model_path: string) => {
    await updateAgent({ model_path });
  };

  const handleAdapterPathUpdate = async (adapter_path: string) => {
    await updateAgent({ adapter_path: adapter_path || undefined });
  };

  const handleSystemInstructionsUpdate = async (system_instructions: string) => {
    await updateAgent({ system_instructions });
    setShowSystemInstructionsModal(false);
  };

  const handleLLMConfigUpdate = async (updates: Partial<typeof agent.llm_config>) => {
    await updateAgent({
      llm_config: {
        ...agent.llm_config,
        ...updates,
      },
    });
  };

  const handleEmbeddingConfigUpdate = async (updates: Partial<typeof agent.embedding_config>) => {
    await updateAgent({
      embedding_config: {
        ...agent.embedding_config,
        ...updates,
      },
    });
  };

  const handleClone = async () => {
    const newAgent = await cloneAgent();
    if (newAgent && onClone) {
      onClone(newAgent.id);
    }
  };

  const handleDelete = async () => {
    if (confirm(`Are you sure you want to delete "${agent.name}"?`)) {
      await deleteAgent();
      if (onDelete) {
        onDelete();
      }
    }
  };

  const handleCreateAgent = () => {
    alert('Create agent functionality coming soon!');
    // TODO: Implement create agent modal
  };

  const handleManageAgents = () => {
    alert('Manage agents functionality coming soon!');
    // TODO: Implement manage agents modal or page
  };

  return (
    <div className="agent-settings">
      <div className="agent-settings-header-label">AGENT SETTINGS</div>

      <AgentHeader
        name={agent.name}
        onNameUpdate={handleNameUpdate}
        onClone={handleClone}
        onDelete={handleDelete}
        onExport={exportAgent}
      />

      <AgentManagement
        agentId={agentId}
        onCreateAgent={handleCreateAgent}
        onManageAgents={handleManageAgents}
      />

      <div className="agent-settings-content">
        <EditableField
          label="Name"
          value={agent.name}
          onSave={handleNameUpdate}
        />

        <EditableField
          label="Description"
          value={agent.description || ''}
          onSave={handleDescriptionUpdate}
          helpText="A brief description of this agent's purpose"
        />

        <LLMConfig
          config={agent.llm_config}
          onUpdate={handleLLMConfigUpdate}
          modelPath={agent.model_path}
          adapterPath={agent.adapter_path || ''}
          systemInstructions={agent.system_instructions}
          onModelPathUpdate={handleModelPathUpdate}
          onAdapterPathUpdate={handleAdapterPathUpdate}
          onSystemInstructionsClick={() => setShowSystemInstructionsModal(true)}
        />

        <EmbeddingConfig
          config={agent.embedding_config}
          onUpdate={handleEmbeddingConfigUpdate}
        />
      </div>

      {showSystemInstructionsModal && (
        <SystemInstructionsModal
          value={agent.system_instructions}
          onSave={handleSystemInstructionsUpdate}
          onClose={() => setShowSystemInstructionsModal(false)}
        />
      )}
    </div>
  );
}

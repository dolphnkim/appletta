import { useState } from 'react';
import { useAgent } from '../../hooks/useAgent';
import { agentAPI } from '../../api/agentAPI';
import AgentHeader from './AgentHeader';
import EditableField from './EditableField';
import SystemInstructionsModal from './SystemInstructionsModal';
import AgentManagement from './AgentManagement';
import AgentAttachments from './AgentAttachments';
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

  // Helper function to handle template save-as logic
  const handleTemplateUpdate = async (updates: any) => {
    if (!agent.is_template) {
      // Regular agent: just update
      return await updateAgent(updates);
    }

    // Template agent: create new agent (save-as)
    try {
      // Determine the name for the new agent
      let newName = 'New Agent (copy)';
      if (updates.name && updates.name !== agent.name) {
        newName = updates.name;
      }

      // Create new agent with all current settings + updates
      const newAgent = await agentAPI.create({
        name: newName,
        description: updates.description ?? agent.description ?? '',
        agent_type: updates.agent_type ?? agent.agent_type,
        is_template: false, // New agent is not a template
        enabled_tools: updates.enabled_tools ?? agent.enabled_tools ?? [],
        model_path: updates.model_path ?? agent.model_path,
        adapter_path: updates.adapter_path ?? agent.adapter_path,
        system_instructions: updates.system_instructions ?? agent.system_instructions,
        llm_config: updates.llm_config ? { ...agent.llm_config, ...updates.llm_config } : agent.llm_config,
        embedding_config: updates.embedding_config ? { ...agent.embedding_config, ...updates.embedding_config } : agent.embedding_config,
      });

      // Navigate to the new agent
      if (newAgent && onClone) {
        onClone(newAgent.id);
      }

      return newAgent;
    } catch (err) {
      console.error('Failed to save template as new agent:', err);
      throw err;
    }
  };

  const handleNameUpdate = async (name: string) => {
    await handleTemplateUpdate({ name });
  };

  const handleDescriptionUpdate = async (description: string) => {
    await handleTemplateUpdate({ description });
  };

  const handleAgentTypeUpdate = async (agent_type: string) => {
    await handleTemplateUpdate({ agent_type });
  };

  const handleModelPathUpdate = async (model_path: string) => {
    await handleTemplateUpdate({ model_path });
  };

  const handleAdapterPathUpdate = async (adapter_path: string) => {
    await handleTemplateUpdate({ adapter_path: adapter_path || undefined });
  };

  const handleSystemInstructionsUpdate = async (system_instructions: string) => {
    await handleTemplateUpdate({ system_instructions });
    setShowSystemInstructionsModal(false);
  };

  const handleLLMConfigUpdate = async (updates: Partial<typeof agent.llm_config>) => {
    await handleTemplateUpdate({
      llm_config: {
        ...agent.llm_config,
        ...updates,
      },
    });
  };

  const handleEmbeddingConfigUpdate = async (updates: Partial<typeof agent.embedding_config>) => {
    await handleTemplateUpdate({
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
    if (agent.is_template) {
      alert('Cannot delete the template agent. This agent serves as the starting point for new agents.');
      return;
    }

    if (confirm(`Are you sure you want to delete "${agent.name}"?`)) {
      await deleteAgent();
      if (onDelete) {
        onDelete();
      }
    }
  };

  const handleCreateAgent = async () => {
    try {
      // Find the template agent
      const agents = await agentAPI.list();
      const templateAgent = agents.find(a => a.is_template);

      if (templateAgent && onClone) {
        // Navigate to the template agent
        onClone(templateAgent.id);
      } else {
        alert('New Agent template not found. Please ensure the template exists.');
      }
    } catch (err) {
      console.error('Failed to navigate to template:', err);
      alert(`Failed to navigate to template: ${err instanceof Error ? err.message : 'Unknown error'}`);
    }
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

        <div className="settings-field">
          <label className="settings-label">
            Agent Type
            <span className="help-text">The role this agent plays in the system</span>
          </label>
          <select
            className="settings-select"
            value={agent.agent_type}
            onChange={(e) => handleAgentTypeUpdate(e.target.value)}
          >
            <option value="main">Main</option>
            <option value="memory">Memory</option>
            <option value="tool">Tool</option>
            <option value="reflection">Reflection</option>
            <option value="other">Other</option>
          </select>
        </div>

        <AgentManagement
          agentId={agentId}
          onCreateAgent={handleCreateAgent}
          onManageAgents={handleManageAgents}
        />

        <div className="settings-section">
          <div className="settings-section-title">Attached Agents</div>
          <AgentAttachments
            agentId={agentId}
            onCreateAgent={handleCreateAgent}
            onManageAgents={handleManageAgents}
          />
        </div>

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

import { useState } from 'react';
import { useAgent } from '../../hooks/useAgent';
import { agentAPI } from '../../api/agentAPI';
import AgentHeader from './AgentHeader';
import EditableField from './EditableField';
import ProjectInstructionsModal from './ProjectInstructionsModal';
import LocalSettingsModal from './LocalSettingsModal';
import AgentManagement from './AgentManagement';
import AgentAttachments from './AgentAttachments';
import LLMConfig from './LLMConfig';
import EmbeddingConfig from './EmbeddingConfig';
import FreeChoiceConfig from './FreeChoiceConfig';
import './AgentSettings.css';

interface AgentSettingsProps {
  agentId: string;
  onDelete?: () => void;
  onClone?: (newAgentId: string) => void;
}

export default function AgentSettings({ agentId, onDelete, onClone }: AgentSettingsProps) {
  const { agent, loading, error, updateAgent, cloneAgent, deleteAgent, exportAgent } = useAgent(agentId);
  const [showProjectInstructionsModal, setShowProjectInstructionsModal] = useState(false);
  const [showLocalSettingsModal, setShowLocalSettingsModal] = useState(false);

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
        adapter_path: 'adapter_path' in updates ? updates.adapter_path : agent.adapter_path,
        project_instructions: updates.project_instructions ?? agent.project_instructions,
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
    // Send null to explicitly clear, undefined to not update, or the path value
    await handleTemplateUpdate({ adapter_path: adapter_path || null });
  };

  const handleProjectInstructionsUpdate = async (project_instructions: string) => {
    await handleTemplateUpdate({ project_instructions });
    setShowProjectInstructionsModal(false);
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

  const handleFreeChoiceConfigUpdate = async (updates: Partial<typeof agent.free_choice_config>) => {
    await handleTemplateUpdate({
      free_choice_config: {
        ...agent.free_choice_config,
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
      <div className="agent-settings-header-row">
        <div className="agent-settings-header-label">AGENT SETTINGS</div>
        <button
          className="local-settings-button"
          onClick={() => setShowLocalSettingsModal(true)}
          title="Local Settings (default paths)"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
            <path fillRule="evenodd" d="M7.429 1.525a6.593 6.593 0 011.142 0c.036.003.108.036.137.146l.289 1.105c.147.56.55.967.997 1.189.174.086.341.183.501.29.417.278.97.423 1.53.27l1.102-.303c.11-.03.175.016.195.046.219.31.41.641.573.989.014.031.022.11-.059.19l-.815.806c-.411.406-.562.957-.53 1.456a4.588 4.588 0 010 .582c-.032.499.119 1.05.53 1.456l.815.806c.08.08.073.159.059.19a6.494 6.494 0 01-.573.99c-.02.029-.086.074-.195.045l-1.103-.303c-.56-.153-1.113-.008-1.53.27a4.506 4.506 0 01-.5.29c-.449.222-.851.628-.998 1.189l-.289 1.105c-.029.11-.101.143-.137.146a6.613 6.613 0 01-1.142 0c-.036-.003-.108-.037-.137-.146l-.289-1.105c-.147-.56-.55-.967-.997-1.189a4.502 4.502 0 01-.501-.29c-.417-.278-.97-.423-1.53-.27l-1.102.303c-.11.03-.175-.016-.195-.046a6.492 6.492 0 01-.573-.989c-.014-.031-.022-.11.059-.19l.815-.806c.411-.406.562-.957.53-1.456a4.587 4.587 0 010-.582c.032-.499-.119-1.05-.53-1.456l-.815-.806c-.08-.08-.073-.159-.059-.19a6.44 6.44 0 01.573-.99c.02-.029.086-.074.195-.045l1.103.303c.56.153 1.113.008 1.53-.27.16-.107.327-.204.5-.29.449-.222.851-.628.998-1.189l.289-1.105c.029-.11.101-.143.137-.146zM8 0c-.236 0-.47.01-.701.03-.743.065-1.29.615-1.458 1.261l-.29 1.106c-.017.066-.078.158-.211.224a5.994 5.994 0 00-.668.386c-.123.082-.233.09-.3.071L3.27 2.776c-.644-.177-1.392.02-1.82.63a7.977 7.977 0 00-.704 1.217c-.315.675-.111 1.422.363 1.891l.815.806c.05.048.098.147.088.294a6.084 6.084 0 000 .772c.01.147-.037.246-.088.294l-.815.806c-.474.469-.678 1.216-.363 1.891.2.428.436.835.704 1.218.428.609 1.176.806 1.82.63l1.103-.303c.066-.019.176-.011.299.071.213.143.436.272.668.386.133.066.194.158.212.224l.289 1.106c.169.646.715 1.196 1.458 1.26a8.094 8.094 0 001.402 0c.743-.064 1.29-.614 1.458-1.26l.29-1.106c.017-.066.078-.158.211-.224a5.98 5.98 0 00.668-.386c.123-.082.233-.09.3-.071l1.102.302c.644.177 1.392-.02 1.82-.63.268-.382.505-.789.704-1.217.315-.675.111-1.422-.364-1.891l-.814-.806c-.05-.048-.098-.147-.088-.294a6.1 6.1 0 000-.772c-.01-.147.037-.246.088-.294l.814-.806c.475-.469.679-1.216.364-1.891a7.992 7.992 0 00-.704-1.218c-.428-.609-1.176-.806-1.82-.63l-1.103.303c-.066.019-.176.011-.299-.071a5.991 5.991 0 00-.668-.386c-.133-.066-.194-.158-.212-.224L10.16 1.29C9.99.645 9.444.095 8.701.031A8.094 8.094 0 008 0zm1.5 8a1.5 1.5 0 11-3 0 1.5 1.5 0 013 0zM11 8a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
        </button>
      </div>

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
          projectInstructions={agent.project_instructions}
          onModelPathUpdate={handleModelPathUpdate}
          onAdapterPathUpdate={handleAdapterPathUpdate}
          onProjectInstructionsClick={() => setShowProjectInstructionsModal(true)}
        />

        <EmbeddingConfig
          config={agent.embedding_config}
          onUpdate={handleEmbeddingConfigUpdate}
        />

        <FreeChoiceConfig
          config={agent.free_choice_config}
          onUpdate={handleFreeChoiceConfigUpdate}
        />

        {/* Router Logging Toggle */}
        <div className="settings-section">
          <div className="settings-section-title">Router Logging</div>
          <div className="settings-field">
            <label className="settings-label">
              Track Expert Activations
              <span className="help-text">Enable MoE expert tracking during conversations for analysis</span>
            </label>
            <label className="toggle-switch">
              <input
                type="checkbox"
                checked={agent.router_logging_enabled || false}
                onChange={(e) => handleTemplateUpdate({ router_logging_enabled: e.target.checked })}
              />
              <span className="toggle-slider"></span>
              <span className="toggle-label">{agent.router_logging_enabled ? 'On' : 'Off'}</span>
            </label>
          </div>
        </div>
      </div>

      {showProjectInstructionsModal && (
        <ProjectInstructionsModal
          value={agent.project_instructions}
          onSave={handleProjectInstructionsUpdate}
          onClose={() => setShowProjectInstructionsModal(false)}
        />
      )}

      {showLocalSettingsModal && (
        <LocalSettingsModal onClose={() => setShowLocalSettingsModal(false)} />
      )}
    </div>
  );
}

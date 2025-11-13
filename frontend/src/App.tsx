import { useState, useEffect } from 'react';
import LeftPanel from './components/LeftPanel/LeftPanel';
import ChatPanel from './components/ChatPanel/ChatPanel';
import DatabasePanel from './components/DatabasePanel/DatabasePanel';
import type { Agent } from './types/agent';
import './App.css';

function App() {
  // Restore state from localStorage
  const [agentId, setAgentId] = useState<string | null>(() => {
    return localStorage.getItem('selectedAgentId');
  });
  const [agents, setAgents] = useState<Agent[]>([]);
  const [currentConversationId, setCurrentConversationId] = useState<string | undefined>(() => {
    const saved = localStorage.getItem('currentConversationId');
    return saved || undefined;
  });

  // Persist agentId to localStorage
  useEffect(() => {
    if (agentId) {
      localStorage.setItem('selectedAgentId', agentId);
    }
  }, [agentId]);

  // Persist conversationId to localStorage
  useEffect(() => {
    if (currentConversationId) {
      localStorage.setItem('currentConversationId', currentConversationId);
    } else {
      localStorage.removeItem('currentConversationId');
    }
  }, [currentConversationId]);

  // Fetch agents on mount
  useEffect(() => {
    fetchAgents();
  }, []);

  const fetchAgents = async () => {
    try {
      const response = await fetch('http://localhost:8000/api/v1/agents/');
      const agentsData = await response.json();
      setAgents(agentsData);

      // Only set default agent if no agent is selected
      if (agentsData && agentsData.length > 0 && !agentId) {
        // Try to find a non-template agent first
        const nonTemplateAgent = agentsData.find((a: Agent) => !a.is_template);
        setAgentId(nonTemplateAgent ? nonTemplateAgent.id : agentsData[0].id);
      }
    } catch (error) {
      console.error('Failed to fetch agents:', error);
    }
  };

  const handleDelete = () => {
    console.log('Agent deleted');
    // Navigate away or show empty state
  };

  const handleClone = (newAgentId: string) => {
    console.log('Agent cloned:', newAgentId);
    // Switch to the new agent
    setAgentId(newAgentId);
    setCurrentConversationId(undefined); // Clear conversation when switching agents
    // Refresh agents list to include the new agent
    fetchAgents();
  };

  const handleConversationSelect = (conversationId: string) => {
    setCurrentConversationId(conversationId);
  };

  const handleNewConversation = () => {
    // Clear current conversation - ChatPanel will create new one
    setCurrentConversationId(undefined);
  };

  const handleAgentChange = (newAgentId: string) => {
    setAgentId(newAgentId);
    setCurrentConversationId(undefined); // Clear conversation when switching agents
  };

  if (!agentId) {
    return (
      <div className="app" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh' }}>
        <div>Loading agent...</div>
      </div>
    );
  }

  return (
    <div className="app">
      <div className="app-left-panel">
        <LeftPanel
          agentId={agentId}
          currentConversationId={currentConversationId}
          onConversationSelect={handleConversationSelect}
          onNewConversation={handleNewConversation}
          onDelete={handleDelete}
          onClone={handleClone}
        />
      </div>
      <div className="app-center-panel">
        <ChatPanel
          agentId={agentId}
          agents={agents}
          conversationId={currentConversationId}
          onConversationChange={setCurrentConversationId}
          onAgentChange={handleAgentChange}
        />
      </div>
      <div className="app-right-panel">
        <DatabasePanel agentId={agentId} />
      </div>
    </div>
  );
}

export default App;

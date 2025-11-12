import { useState, useEffect } from 'react';
import LeftPanel from './components/LeftPanel/LeftPanel';
import ChatPanel from './components/ChatPanel/ChatPanel';
import DatabasePanel from './components/DatabasePanel/DatabasePanel';
import './App.css';

function App() {
  const [agentId, setAgentId] = useState<string | null>(null);
  const [currentConversationId, setCurrentConversationId] = useState<string | undefined>();

  // Fetch first available agent on mount
  useEffect(() => {
    const fetchAgent = async () => {
      try {
        const response = await fetch('http://localhost:8000/api/v1/agents/');
        const agents = await response.json();
        if (agents && agents.length > 0) {
          setAgentId(agents[0].id);
        }
      } catch (error) {
        console.error('Failed to fetch agents:', error);
      }
    };
    fetchAgent();
  }, []);

  const handleDelete = () => {
    console.log('Agent deleted');
    // Navigate away or show empty state
  };

  const handleClone = (newAgentId: string) => {
    console.log('Agent cloned:', newAgentId);
    // Navigate to new agent or update state
  };

  const handleConversationSelect = (conversationId: string) => {
    setCurrentConversationId(conversationId);
  };

  const handleNewConversation = () => {
    // Clear current conversation - ChatPanel will create new one
    setCurrentConversationId(undefined);
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
          conversationId={currentConversationId}
          onConversationChange={setCurrentConversationId}
        />
      </div>
      <div className="app-right-panel">
        <DatabasePanel agentId={agentId} />
      </div>
    </div>
  );
}

export default App;

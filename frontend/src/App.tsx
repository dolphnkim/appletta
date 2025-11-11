import { useState } from 'react';
import { LeftPanel } from './components/LeftPanel';
import { ChatPanel } from './components/ChatPanel';
import { DatabasePanel } from './components/DatabasePanel';
import './App.css';

function App() {
  // For now, we'll use a demo agent ID
  // In production, this would come from routing or props
  const demoAgentId = 'demo-agent-123';

  const [currentConversationId, setCurrentConversationId] = useState<string | undefined>();

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

  return (
    <div className="app">
      <div className="app-left-panel">
        <LeftPanel
          agentId={demoAgentId}
          currentConversationId={currentConversationId}
          onConversationSelect={handleConversationSelect}
          onNewConversation={handleNewConversation}
          onDelete={handleDelete}
          onClone={handleClone}
        />
      </div>
      <div className="app-center-panel">
        <ChatPanel
          agentId={demoAgentId}
          conversationId={currentConversationId}
          onConversationChange={setCurrentConversationId}
        />
      </div>
      <div className="app-right-panel">
        <DatabasePanel agentId={demoAgentId} />
      </div>
    </div>
  );
}

export default App;

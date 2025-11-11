import AgentSettings from './components/AgentSettings/AgentSettings';
import { DatabasePanel } from './components/DatabasePanel';
import './App.css';

function App() {
  // For now, we'll use a demo agent ID
  // In production, this would come from routing or props
  const demoAgentId = 'demo-agent-123';

  const handleDelete = () => {
    console.log('Agent deleted');
    // Navigate away or show empty state
  };

  const handleClone = (newAgentId: string) => {
    console.log('Agent cloned:', newAgentId);
    // Navigate to new agent or update state
  };

  return (
    <div className="app">
      <div className="app-left-panel">
        <AgentSettings
          agentId={demoAgentId}
          onDelete={handleDelete}
          onClone={handleClone}
        />
      </div>
      <div className="app-right-panel">
        <DatabasePanel agentId={demoAgentId} />
      </div>
    </div>
  );
}

export default App;

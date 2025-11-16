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

  // Column widths (in percentages)
  const [leftWidth, setLeftWidth] = useState(() => {
    const saved = localStorage.getItem('leftPanelWidth');
    return saved ? parseInt(saved) : 20;
  });
  const [rightWidth, setRightWidth] = useState(() => {
    const saved = localStorage.getItem('rightPanelWidth');
    return saved ? parseInt(saved) : 25;
  });
  const [isDraggingLeft, setIsDraggingLeft] = useState(false);
  const [isDraggingRight, setIsDraggingRight] = useState(false);

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

  // Persist panel widths to localStorage
  useEffect(() => {
    localStorage.setItem('leftPanelWidth', leftWidth.toString());
  }, [leftWidth]);

  useEffect(() => {
    localStorage.setItem('rightPanelWidth', rightWidth.toString());
  }, [rightWidth]);

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

  // Resizing handlers
  const handleMouseMoveLeft = (e: MouseEvent) => {
    if (!isDraggingLeft) return;
    const newWidth = (e.clientX / window.innerWidth) * 100;
    if (newWidth > 10 && newWidth < 40) {
      setLeftWidth(newWidth);
    }
  };

  const handleMouseMoveRight = (e: MouseEvent) => {
    if (!isDraggingRight) return;
    const newWidth = ((window.innerWidth - e.clientX) / window.innerWidth) * 100;
    if (newWidth > 15 && newWidth < 45) {
      setRightWidth(newWidth);
    }
  };

  const handleMouseUp = () => {
    setIsDraggingLeft(false);
    setIsDraggingRight(false);
  };

  useEffect(() => {
    if (isDraggingLeft || isDraggingRight) {
      const handleMove = (e: MouseEvent) => {
        if (isDraggingLeft) handleMouseMoveLeft(e);
        if (isDraggingRight) handleMouseMoveRight(e);
      };

      document.addEventListener('mousemove', handleMove);
      document.addEventListener('mouseup', handleMouseUp);

      return () => {
        document.removeEventListener('mousemove', handleMove);
        document.removeEventListener('mouseup', handleMouseUp);
      };
    }
  }, [isDraggingLeft, isDraggingRight, leftWidth, rightWidth]);

  if (!agentId) {
    return (
      <div className="app" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh' }}>
        <div>Loading agent...</div>
      </div>
    );
  }

  const centerWidth = 100 - leftWidth - rightWidth;

  return (
    <div className="app">
      <button
        className="home-button"
        title="Back to dashboard"
        onClick={() => {
          // TODO: Navigate to dashboard when it exists
          console.log('Navigate to dashboard');
        }}
      >
        🏠
      </button>
      <div className="app-left-panel" style={{ width: `${leftWidth}%` }}>
        <LeftPanel
          agentId={agentId}
          currentConversationId={currentConversationId}
          onConversationSelect={handleConversationSelect}
          onNewConversation={handleNewConversation}
          onDelete={handleDelete}
          onClone={handleClone}
        />
      </div>
      <div
        className="app-resize-handle"
        onMouseDown={() => setIsDraggingLeft(true)}
      />
      <div className="app-center-panel" style={{ width: `${centerWidth}%` }}>
        <ChatPanel
          agentId={agentId}
          agents={agents}
          conversationId={currentConversationId}
          onConversationChange={setCurrentConversationId}
          onAgentChange={handleAgentChange}
        />
      </div>
      <div
        className="app-resize-handle"
        onMouseDown={() => setIsDraggingRight(true)}
      />
      <div className="app-right-panel" style={{ width: `${rightWidth}%` }}>
        <DatabasePanel agentId={agentId} />
      </div>
    </div>
  );
}

export default App;

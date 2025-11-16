import { useNavigate } from 'react-router-dom';
import TrainingPanel from '../components/TrainingPanel/TrainingPanel';
import './TrainingView.css';

export default function TrainingView() {
  const navigate = useNavigate();
  const agentId = localStorage.getItem('selectedAgentId') || '';

  return (
    <div className="training-view">
      <header className="training-view-header">
        <button className="back-button" onClick={() => navigate('/')}>
          ← Back to Dashboard
        </button>
        <h2>🧪 Training Lab</h2>
      </header>

      <div className="training-view-content">
        <TrainingPanel agentId={agentId} />
      </div>
    </div>
  );
}

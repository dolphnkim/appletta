import { useEffect, useRef } from 'react';
import { agentAPI } from '../api/agentAPI';
import type { Agent } from '../types/agent';

interface UseFreeChoiceTimerProps {
  agent: Agent | null;
  isActiveConversation: boolean; // Don't trigger if user is chatting
  onSessionStarted?: (conversationId: string) => void;
}

/**
 * Hook that periodically checks if a free choice session should start.
 * Polls every minute to check if enough time has passed.
 */
export function useFreeChoiceTimer({
  agent,
  isActiveConversation,
  onSessionStarted,
}: UseFreeChoiceTimerProps) {
  const lastCheckRef = useRef<string | null>(null);

  useEffect(() => {
    if (!agent || !agent.free_choice_config.enabled || isActiveConversation) {
      return;
    }

    const checkFreeChoice = async () => {
      try {
        const result = await agentAPI.startFreeChoiceSession(agent.id);

        if (result.status === 'started' && result.conversation_id) {
          console.log('Free choice session started:', result.conversation_id);
          if (onSessionStarted) {
            onSessionStarted(result.conversation_id);
          }
        } else if (result.status === 'too_soon') {
          console.log('Free choice session:', result.message);
        }
      } catch (error) {
        console.error('Failed to check free choice session:', error);
      }
    };

    // Check immediately on mount (if enabled)
    const now = new Date().toISOString();
    if (lastCheckRef.current !== now) {
      checkFreeChoice();
      lastCheckRef.current = now;
    }

    // Then check every minute
    const intervalId = setInterval(checkFreeChoice, 60 * 1000);

    return () => clearInterval(intervalId);
  }, [agent, isActiveConversation, onSessionStarted]);
}

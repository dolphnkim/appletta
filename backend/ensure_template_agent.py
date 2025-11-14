"""Ensure the New Agent template exists in the database"""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session
from backend.db.session import SessionLocal
from backend.db.models.agent import Agent

def ensure_template_agent():
    """Create or update the New Agent template"""
    db: Session = SessionLocal()

    try:
        # Check if New Agent template already exists
        template = db.query(Agent).filter(
            Agent.name == "New Agent",
            Agent.is_template == True
        ).first()

        if template:
            # Update template if it has empty system instructions
            if not template.project_instructions or len(template.project_instructions.strip()) == 0:
                template.project_instructions = "You are...."
                db.commit()
                print("✅ Updated New Agent template with default system instructions")
            else:
                print("✅ New Agent template already exists")
            return

        # Check if there's a non-template "New Agent"
        existing_agent = db.query(Agent).filter(Agent.name == "New Agent").first()

        if existing_agent:
            # Update it to be a template
            existing_agent.is_template = True
            db.commit()
            print("✅ Updated existing 'New Agent' to be a template")
            return

        # Get any existing agent as a template for default values
        sample_agent = db.query(Agent).first()

        if not sample_agent:
            print("⚠️  No agents exist yet. Please create at least one agent first.")
            print("   The first agent created will be used as a template for default values.")
            return

        # Create the New Agent template based on the first agent
        new_template = Agent(
            name="New Agent",
            description="",
            agent_type="main",
            is_template=True,
            model_path=sample_agent.model_path,
            adapter_path=sample_agent.adapter_path,
            project_instructions="You are...",
            reasoning_enabled=sample_agent.reasoning_enabled,
            temperature=sample_agent.temperature,
            top_p=sample_agent.top_p,
            top_k=sample_agent.top_k,
            seed=sample_agent.seed,
            max_output_tokens_enabled=sample_agent.max_output_tokens_enabled,
            max_output_tokens=sample_agent.max_output_tokens,
            max_context_tokens=sample_agent.max_context_tokens,
            embedding_model_path=sample_agent.embedding_model_path,
            embedding_dimensions=sample_agent.embedding_dimensions,
            embedding_chunk_size=sample_agent.embedding_chunk_size,
        )

        db.add(new_template)
        db.commit()
        print("✅ Created New Agent template")

    except Exception as e:
        print(f"❌ Error ensuring template agent: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    ensure_template_agent()

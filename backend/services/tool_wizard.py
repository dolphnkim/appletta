"""Tool Wizard - Choose-Your-Own-Adventure style tool interaction

This system allows ANY model (even tiny ones) to use tools through
a guided text-based conversation flow instead of structured function calling.

Key features:
- Works with models that don't support OpenAI-style function calling
- Clear, numbered options at each step
- Supports looping up to MAX_ITERATIONS times
- Falls back to normal chat after iterations exhausted
"""

from typing import Optional, Dict, Any, List, Tuple
from sqlalchemy.orm import Session
from backend.db.models.journal_block import JournalBlock
from backend.services.tools import list_journal_blocks, create_journal_block, update_journal_block
from backend.services.memory_service import search_memories

MAX_ITERATIONS = 5


class WizardState:
    """Tracks where we are in the wizard conversation"""

    def __init__(self, data: Optional[Dict[str, Any]] = None):
        if data is None:
            data = {}

        self.step = data.get("step", "main_menu")  # Current step in the flow
        self.tool = data.get("tool", None)  # Which tool are we using (create, edit, search)
        self.iteration = data.get("iteration", 0)  # How many times have we looped
        self.context = data.get("context", {})  # Tool-specific context
        self.tool_use_log = data.get("tool_use_log", [])  # Log of what tools have been used

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step,
            "tool": self.tool,
            "iteration": self.iteration,
            "context": self.context,
            "tool_use_log": self.tool_use_log
        }

    def increment_iteration(self):
        self.iteration += 1

    def log_tool_use(self, action: str):
        """Log a tool action that was completed"""
        self.tool_use_log.append(action)
        print(f"   📝 LOGGED: {action}")

    def get_tool_use_summary(self) -> str:
        """Get a summary of tools used so far this turn"""
        if not self.tool_use_log:
            return ""
        summary = "\n=== ACTIONS COMPLETED THIS TURN ===\n"
        for i, action in enumerate(self.tool_use_log, 1):
            summary += f"{i}. {action}\n"
        summary += "===================================\n\n"
        return summary

    def is_exhausted(self) -> bool:
        return self.iteration >= MAX_ITERATIONS

    def reset_to_menu(self):
        """Reset to main menu for next iteration"""
        self.step = "main_menu"
        self.tool = None
        self.context = {}


def get_wizard_state(message_metadata: Optional[Dict[str, Any]]) -> WizardState:
    """Extract wizard state from message metadata"""
    if not message_metadata:
        return WizardState()

    wizard_data = message_metadata.get("wizard_state", {})
    return WizardState(wizard_data)


def clean_llm_response(response: str) -> str:
    """
    Clean up LLM response to extract just the actual answer.
    Removes:
    - Thinking tags and their content

    NOTE: Preserves ALL content after thinking tags, including multi-line text.
    This is important for journal block content which can be long.
    """
    import re

    cleaned = response.strip()

    # Remove thinking tags and everything before them
    if "</think>" in cleaned:
        # Take only what's after the last </think> tag
        cleaned = cleaned.split("</think>")[-1].strip()

    # Remove <think> tags if they exist without closing
    cleaned = re.sub(r'<think>.*', '', cleaned, flags=re.DOTALL)

    return cleaned.strip()


def show_main_menu() -> str:
    """Generate the main menu prompt"""
    return """MANDATORY: Before responding to the user, you MUST select ONE option below.

RESPOND WITH ONLY THE NUMBER OF YOUR CHOICE:

1. Chat normally (no tools) - Just respond to the user's message
2. Create new journal block - Store information in your memory
3. Edit existing journal block - Modify stored information
4. Read a journal block - View stored information
5. Delete a journal block - Remove stored information
6. Search my memories - Look for past conversations
7. List my uploaded files (RAG) - See available documents

YOUR RESPONSE MUST BE A SINGLE NUMBER (1-7). NO OTHER TEXT."""


def parse_choice(response: str) -> Optional[int]:
    """Extract numeric choice from AI response"""
    # Try to find the first number in the response
    import re
    match = re.search(r'\b([1-7])\b', response)
    if match:
        return int(match.group(1))
    return None


async def process_wizard_step(
    user_message: str,
    wizard_state: WizardState,
    agent_id: str,
    db: Session
) -> Tuple[str, WizardState, bool]:
    """
    Process one step of the wizard interaction

    Returns:
        (prompt_to_show, updated_wizard_state, should_continue_wizard)
    """

    # Clean the LLM response to extract just the answer
    # This removes thinking tags, code blocks, quotes, etc.
    original_message = user_message
    user_message = clean_llm_response(user_message)
    print(f"   🧹 CLEANED RESPONSE: '{user_message}' (from: '{original_message[:50]}...')")

    # Check if we've exhausted iterations
    if wizard_state.is_exhausted():
        return ("You've used all your tool actions for now. Let's chat normally!",
                WizardState(), False)

    # Main menu - figure out what they want to do
    if wizard_state.step == "main_menu":
        choice = parse_choice(user_message)

        # Map choice to human-readable option
        choice_map = {
            1: "Chat normally (no tools)",
            2: "Create new journal block",
            3: "Edit existing journal block",
            4: "Read a journal block",
            5: "Delete a journal block",
            6: "Search memories",
            7: "List RAG files"
        }
        choice_name = choice_map.get(choice, f"INVALID ({choice})")
        print(f"\n🎯 LLM CHOSE OPTION: {choice} - {choice_name}")

        if choice == 1:
            # Chat normally - exit wizard
            print(f"   ➡️  Exiting wizard, will proceed to normal chat")
            return ("", WizardState(), False)

        elif choice == 2:
            # Create new journal block
            print(f"   ➡️  Starting create journal block flow")
            wizard_state.tool = "create"
            wizard_state.step = "create_label"
            return ("What should the label/title be for this journal block?\n\nRESPOND WITH ONLY THE LABEL TEXT. Maximum 50 characters. No quotes, no explanation, just the label itself.",
                    wizard_state, True)

        elif choice == 3:
            # Edit existing journal block - list them first
            print(f"   ➡️  Starting edit journal block flow")
            from uuid import UUID as UUIDType
            blocks_info = list_journal_blocks(UUIDType(agent_id), db)
            blocks = blocks_info.get("blocks", [])

            if not blocks:
                print(f"   ⚠️  No journal blocks exist")
                wizard_state.reset_to_menu()
                wizard_state.increment_iteration()
                return ("You don't have any journal blocks yet!\n\n" + show_main_menu(),
                        wizard_state, True)

            # Store blocks in context and show them
            wizard_state.tool = "edit"
            wizard_state.step = "edit_select_block"
            wizard_state.context["blocks"] = blocks

            prompt = "Which journal block would you like to edit?\n\n"
            for i, block in enumerate(blocks, 1):
                prompt += f"{i}. {block['label']}\n"
            prompt += "\nRESPOND WITH ONLY THE NUMBER. No text, no explanation, just the number."

            return (prompt, wizard_state, True)

        elif choice == 4:
            # Read a journal block - list them first
            print(f"   ➡️  Starting read journal block flow")
            from uuid import UUID as UUIDType
            blocks_info = list_journal_blocks(UUIDType(agent_id), db)
            blocks = blocks_info.get("blocks", [])

            if not blocks:
                print(f"   ⚠️  No journal blocks exist")
                wizard_state.reset_to_menu()
                wizard_state.increment_iteration()
                return ("You don't have any journal blocks yet!\n\n" + show_main_menu(),
                        wizard_state, True)

            wizard_state.tool = "read"
            wizard_state.step = "read_select_block"
            wizard_state.context["blocks"] = blocks

            prompt = "Which journal block would you like to read?\n\n"
            for i, block in enumerate(blocks, 1):
                prompt += f"{i}. {block['label']}\n"
            prompt += "\nRESPOND WITH ONLY THE NUMBER. No text, no explanation, just the number."

            return (prompt, wizard_state, True)

        elif choice == 5:
            # Delete a journal block - list them first
            print(f"   ➡️  Starting delete journal block flow")
            from uuid import UUID as UUIDType
            blocks_info = list_journal_blocks(UUIDType(agent_id), db)
            blocks = blocks_info.get("blocks", [])

            if not blocks:
                print(f"   ⚠️  No journal blocks exist")
                wizard_state.reset_to_menu()
                wizard_state.increment_iteration()
                return ("You don't have any journal blocks yet!\n\n" + show_main_menu(),
                        wizard_state, True)

            wizard_state.tool = "delete"
            wizard_state.step = "delete_select_block"
            wizard_state.context["blocks"] = blocks

            prompt = "Which journal block would you like to delete?\n\n"
            for i, block in enumerate(blocks, 1):
                prompt += f"{i}. {block['label']}\n"
            prompt += "\nRESPOND WITH ONLY THE NUMBER. No text, no explanation, just the number."

            return (prompt, wizard_state, True)

        elif choice == 6:
            # Search memories
            print(f"   ➡️  Starting search memories flow")
            wizard_state.tool = "search"
            wizard_state.step = "search_query"
            return ("What would you like to search for in your memories?\n\nRESPOND WITH ONLY THE SEARCH QUERY. Maximum 100 characters. No quotes, no explanation.",
                    wizard_state, True)

        elif choice == 7:
            # List RAG files
            print(f"   ➡️  Listing RAG files")
            from backend.services.tools import list_rag_files
            rag_info = list_rag_files(agent_id, db)

            if "error" in rag_info:
                result_msg = f"❌ TOOL FAILURE: {rag_info['error']}"
                wizard_state.log_tool_use(f"FAILED to list RAG files")
                response = f"{result_msg}\n\n{wizard_state.get_tool_use_summary()}" + show_main_menu()
            elif rag_info.get("total_files", 0) == 0:
                result_msg = "✅ TOOL SUCCESS: Listed RAG files - No uploaded files yet"
                wizard_state.log_tool_use(f"Listed RAG files - No files uploaded")
                response = f"{result_msg}\n\n{wizard_state.get_tool_use_summary()}" + show_main_menu()
            else:
                result_msg = f"✅ TOOL SUCCESS: Listed RAG files - Found {rag_info.get('total_files', 0)} files in {rag_info.get('total_folders', 0)} folders"
                wizard_state.log_tool_use(f"Listed RAG files - Found {rag_info.get('total_files', 0)} files")
                response = f"{result_msg}\n\nHere are your uploaded files:\n\n"
                for folder in rag_info.get("folders", []):
                    response += f"📁 {folder['folder_name']} ({folder['file_count']} files)\n"
                for file in rag_info.get("files", []):
                    response += f"  📄 {file['filename']}\n"
                response += f"\n{wizard_state.get_tool_use_summary()}" + show_main_menu()

            wizard_state.reset_to_menu()
            wizard_state.increment_iteration()
            return (response, wizard_state, True)

        else:
            # Invalid choice
            print(f"   ❌ INVALID CHOICE - LLM response was: {user_message[:100]}")
            return ("I didn't understand that choice. " + show_main_menu(),
                    wizard_state, True)

    # === CREATE JOURNAL BLOCK FLOW ===
    elif wizard_state.step == "create_label":
        # They provided the label - enforce 50 char limit
        label = user_message.strip()

        if len(label) > 50:
            print(f"   ❌ LABEL TOO LONG: {len(label)} chars (max 50)")
            return (f"❌ Label too long! You typed {len(label)} characters, but the maximum is 50.\n\nRESPOND WITH ONLY THE LABEL TEXT. Maximum 50 characters. No quotes, no explanation, just the label itself.",
                    wizard_state, True)

        wizard_state.context["label"] = label
        wizard_state.step = "create_content"
        print(f"   📝 LABEL SET: '{label}'")
        # Skip description - go straight to content
        return (f"Label set to: '{label}'\n\nNow, what content should go in this journal block?\n\nRESPOND WITH ONLY THE CONTENT TEXT. No quotes, no explanation, just the content itself.",
                wizard_state, True)

    elif wizard_state.step == "create_content":
        # They provided the content - create the block!
        wizard_state.context["content"] = user_message.strip()

        # Verify we have the label from previous step
        if "label" not in wizard_state.context:
            print(f"   ❌ BUG: Label not in context! Context: {wizard_state.context}")
            return ("❌ Something went wrong - label was lost. Let's start over.\n\n" + show_main_menu(),
                    WizardState(), True)

        label = wizard_state.context["label"]
        content = wizard_state.context["content"]

        print(f"   📦 CREATING BLOCK: label='{label}', content='{content[:50]}...'")

        # Create the block (agent_id, label, value, db)
        from uuid import UUID as UUIDType
        new_block = create_journal_block(
            UUIDType(agent_id),  # Convert string to UUID
            label,
            content,
            db
        )

        # Add explicit success/failure message BEFORE resetting state
        if "error" in new_block:
            result_msg = f"❌ TOOL FAILURE: {new_block['error']}"
            wizard_state.log_tool_use(f"FAILED to create journal block '{label}'")
        else:
            result_msg = f"✅ TOOL SUCCESS: Created journal block '{new_block['label']}' (ID: {new_block.get('id', 'unknown')})"
            wizard_state.log_tool_use(f"Created journal block '{new_block['label']}'")

        # Done - back to main menu (AFTER logging the action)
        wizard_state.reset_to_menu()
        wizard_state.increment_iteration()

        return (f"{result_msg}\n\n{wizard_state.get_tool_use_summary()}" + show_main_menu(),
                wizard_state, True)

    # === EDIT JOURNAL BLOCK FLOW ===
    elif wizard_state.step == "edit_select_block":
        # They selected which block to edit
        choice = parse_choice(user_message)
        blocks = wizard_state.context.get("blocks", [])

        if choice is None or choice < 1 or choice > len(blocks):
            return ("Invalid choice. Please enter a number from the list.",
                    wizard_state, True)

        selected_block_summary = blocks[choice - 1]

        # Read the full block content (the list only has id/label/updated_at)
        from backend.services.tools import read_journal_block
        full_block = read_journal_block(selected_block_summary["id"], db)

        if "error" in full_block:
            return (f"❌ Error reading block: {full_block['error']}\n\n" + show_main_menu(),
                    wizard_state, True)

        wizard_state.context["selected_block"] = full_block
        wizard_state.step = "edit_select_mode"

        prompt = f"""How would you like to edit "{full_block['label']}"?

Current content:
{full_block['value']}

Choose an editing mode:
1. Search and replace text
2. Completely rewrite this block
3. Append new text to the end

RESPOND WITH ONLY THE NUMBER (1, 2, or 3). No other text."""

        return (prompt, wizard_state, True)

    elif wizard_state.step == "edit_select_mode":
        # They selected the editing mode
        choice = parse_choice(user_message)

        if choice == 1:
            # Search and replace
            wizard_state.step = "edit_search_find"
            return ("What text would you like to find/replace?\n\nRESPOND WITH ONLY THE TEXT TO FIND. No quotes, no explanation.", wizard_state, True)

        elif choice == 2:
            # Complete rewrite
            wizard_state.step = "edit_rewrite"
            return ("Enter the new content for this journal block:\n\nRESPOND WITH ONLY THE NEW CONTENT. No quotes, no explanation.", wizard_state, True)

        elif choice == 3:
            # Append
            wizard_state.step = "edit_append"
            return ("What would you like to add to the end?\n\nRESPOND WITH ONLY THE TEXT TO APPEND. No quotes, no explanation.", wizard_state, True)

        else:
            return ("Invalid choice. Please enter 1, 2, or 3.", wizard_state, True)

    elif wizard_state.step == "edit_search_find":
        # They provided text to find
        wizard_state.context["find_text"] = user_message.strip()
        wizard_state.step = "edit_search_replace"
        return (f"Found: '{user_message.strip()}'\n\nWhat should it be replaced with?\n\nRESPOND WITH ONLY THE REPLACEMENT TEXT. No quotes, no explanation.", wizard_state, True)

    elif wizard_state.step == "edit_search_replace":
        # They provided replacement text - do the replacement
        find_text = wizard_state.context["find_text"]
        replace_text = user_message.strip()
        block = wizard_state.context["selected_block"]

        new_content = block["value"].replace(find_text, replace_text)

        # Update the block (block_id, label, value, db)
        updated_block = update_journal_block(
            block["id"],
            None,  # Don't change label
            new_content,
            db
        )

        wizard_state.reset_to_menu()
        wizard_state.increment_iteration()

        # Add explicit success/failure message
        if "error" in updated_block:
            result_msg = f"❌ TOOL FAILURE: {updated_block['error']}"
            wizard_state.log_tool_use(f"FAILED to update journal block '{block['label']}'")
        else:
            result_msg = f"✅ TOOL SUCCESS: Updated journal block '{block['label']}' (search/replace)"
            wizard_state.log_tool_use(f"Updated journal block '{block['label']}' (search/replace)")

        return (f"{result_msg}\n\n{wizard_state.get_tool_use_summary()}" + show_main_menu(),
                wizard_state, True)

    elif wizard_state.step == "edit_rewrite":
        # Complete rewrite
        block = wizard_state.context["selected_block"]
        new_content = user_message.strip()

        # Update the block (block_id, label, value, db)
        updated_block = update_journal_block(
            block["id"],
            None,  # Don't change label
            new_content,
            db
        )

        wizard_state.reset_to_menu()
        wizard_state.increment_iteration()

        # Add explicit success/failure message
        if "error" in updated_block:
            result_msg = f"❌ TOOL FAILURE: {updated_block['error']}"
            wizard_state.log_tool_use(f"FAILED to rewrite journal block '{block['label']}'")
        else:
            result_msg = f"✅ TOOL SUCCESS: Rewrote journal block '{block['label']}'"
            wizard_state.log_tool_use(f"Rewrote journal block '{block['label']}'")

        return (f"{result_msg}\n\n{wizard_state.get_tool_use_summary()}" + show_main_menu(),
                wizard_state, True)

    elif wizard_state.step == "edit_append":
        # Append to existing content
        block = wizard_state.context["selected_block"]
        append_text = user_message.strip()
        new_content = block["value"] + "\n" + append_text

        # Update the block (block_id, label, value, db)
        updated_block = update_journal_block(
            block["id"],
            None,  # Don't change label
            new_content,
            db
        )

        wizard_state.reset_to_menu()
        wizard_state.increment_iteration()

        # Add explicit success/failure message
        if "error" in updated_block:
            result_msg = f"❌ TOOL FAILURE: {updated_block['error']}"
            wizard_state.log_tool_use(f"FAILED to append to journal block '{block['label']}'")
        else:
            result_msg = f"✅ TOOL SUCCESS: Appended to journal block '{block['label']}'"
            wizard_state.log_tool_use(f"Appended to journal block '{block['label']}'")

        return (f"{result_msg}\n\n{wizard_state.get_tool_use_summary()}" + show_main_menu(),
                wizard_state, True)

    # === READ JOURNAL BLOCK FLOW ===
    elif wizard_state.step == "read_select_block":
        # They selected which block to read
        choice = parse_choice(user_message)
        blocks = wizard_state.context.get("blocks", [])

        if choice is None or choice < 1 or choice > len(blocks):
            return ("Invalid choice. Please enter a number from the list.",
                    wizard_state, True)

        selected_block = blocks[choice - 1]

        # Read the full block content
        from backend.services.tools import read_journal_block
        full_block = read_journal_block(selected_block["id"], db)

        if "error" in full_block:
            result_msg = f"❌ TOOL FAILURE: {full_block['error']}"
            wizard_state.log_tool_use(f"FAILED to read journal block")
            response = f"{result_msg}\n\n{wizard_state.get_tool_use_summary()}" + show_main_menu()
        else:
            result_msg = f"✅ TOOL SUCCESS: Read journal block '{full_block['label']}'"
            wizard_state.log_tool_use(f"Read journal block '{full_block['label']}'")
            response = f"{result_msg}\n\n=== {full_block['label']} ===\n\n{full_block['value']}\n\n{wizard_state.get_tool_use_summary()}" + show_main_menu()

        wizard_state.reset_to_menu()
        wizard_state.increment_iteration()
        return (response, wizard_state, True)

    # === DELETE JOURNAL BLOCK FLOW ===
    elif wizard_state.step == "delete_select_block":
        # They selected which block to delete
        choice = parse_choice(user_message)
        blocks = wizard_state.context.get("blocks", [])

        if choice is None or choice < 1 or choice > len(blocks):
            return ("Invalid choice. Please enter a number from the list.",
                    wizard_state, True)

        selected_block = blocks[choice - 1]

        # Delete the block
        from backend.services.tools import delete_journal_block
        result = delete_journal_block(selected_block["id"], db)

        if "error" in result:
            result_msg = f"❌ TOOL FAILURE: {result['error']}"
            wizard_state.log_tool_use(f"FAILED to delete journal block '{selected_block['label']}'")
        else:
            result_msg = f"✅ TOOL SUCCESS: Deleted journal block '{selected_block['label']}'"
            wizard_state.log_tool_use(f"Deleted journal block '{selected_block['label']}'")

        wizard_state.reset_to_menu()
        wizard_state.increment_iteration()
        return (f"{result_msg}\n\n{wizard_state.get_tool_use_summary()}" + show_main_menu(), wizard_state, True)

    # === SEARCH MEMORIES FLOW ===
    elif wizard_state.step == "search_query":
        # They provided a search query
        query = user_message.strip()

        if len(query) > 100:
            print(f"   ❌ QUERY TOO LONG: {len(query)} chars (max 100)")
            return (f"❌ Search query too long! You typed {len(query)} characters, but the maximum is 100.\n\nRESPOND WITH ONLY THE SEARCH QUERY. Maximum 100 characters. No quotes, no explanation.",
                    wizard_state, True)

        # Search memories
        results = search_memories(
            query_text=query,
            agent_id=agent_id,
            db=db,
            limit=5
        )

        if not results:
            result_msg = f"✅ TOOL SUCCESS: Search completed for '{query}' - No memories found"
            wizard_state.log_tool_use(f"Searched memories for '{query}' - No results")
            response = f"{result_msg}\n\n{wizard_state.get_tool_use_summary()}" + show_main_menu()
        else:
            result_msg = f"✅ TOOL SUCCESS: Search completed for '{query}' - Found {len(results)} memories"
            wizard_state.log_tool_use(f"Searched memories for '{query}' - Found {len(results)} results")
            response = f"{result_msg}\n\nHere's what I found:\n\n"
            for i, result in enumerate(results, 1):
                response += f"{i}. {result['content'][:200]}...\n\n"
            response += f"{wizard_state.get_tool_use_summary()}" + show_main_menu()

        wizard_state.reset_to_menu()
        wizard_state.increment_iteration()
        return (response, wizard_state, True)

    # Unknown step - reset
    else:
        wizard_state = WizardState()
        return ("Something went wrong. " + show_main_menu(), wizard_state, True)

"""Skill loader — scans backend/services/plugins/skills/ for SKILL.md files.

Skills are documented workflows Kevin writes for himself. Unlike plugins (which
add new callable tools), skills are procedures — step-by-step guides for
accomplishing multi-step goals using his existing tools.

Directory layout:
    backend/services/plugins/skills/
        my-skill-name/
            SKILL.md        ← required
        another-skill/
            SKILL.md

Each SKILL.md has optional YAML frontmatter:
    ---
    name: human-readable name
    description: one-line summary shown in the skills index
    ---

    # Body content here...

Skills are loaded fresh from disk on each request (no caching needed — they're
just text files). Call reload_skills to get a live listing of what's loaded.
"""

import re
from pathlib import Path
from typing import Dict, List, Tuple

# backend/services/skill_loader.py → .parent.parent.parent → repo root
SKILLS_DIR: Path = Path(__file__).resolve().parent / "plugins" / "skills"


def load_skills() -> List[Dict[str, str]]:
    """Load all skill docs from SKILLS_DIR.

    Returns a list of dicts:
        {
            "name":        str,   # from frontmatter or dir name
            "description": str,   # from frontmatter or ""
            "content":     str,   # body text (frontmatter stripped)
            "path":        str,   # repo-relative path to the SKILL.md
        }
    """
    skills = []

    if not SKILLS_DIR.exists():
        SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        return skills

    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue

        try:
            raw = skill_md.read_text(encoding="utf-8")
            name, description, content = _parse_skill_md(skill_dir.name, raw)
            repo_root = Path(__file__).resolve().parent.parent.parent
            rel_path = str(skill_md.relative_to(repo_root))
            skills.append({
                "name": name,
                "description": description,
                "content": content,
                "path": rel_path,
            })
        except Exception as e:
            print(f"[skills] Failed to load {skill_md}: {e}")

    return skills


def _parse_skill_md(dir_name: str, raw: str) -> Tuple[str, str, str]:
    """Parse frontmatter + body from a SKILL.md file.

    Returns (name, description, body_content).
    """
    name = dir_name
    description = ""
    content = raw.strip()

    frontmatter_re = re.compile(r"^---\n(.*?)\n---\n?(.*)", re.DOTALL)
    m = frontmatter_re.match(raw)
    if m:
        fm_text = m.group(1)
        content = m.group(2).strip()

        name_m = re.search(r"^name:\s*(.+)$", fm_text, re.MULTILINE)
        if name_m:
            name = name_m.group(1).strip()

        desc_m = re.search(r"^description:\s*(.+)$", fm_text, re.MULTILINE)
        if desc_m:
            description = desc_m.group(1).strip()

    return name, description, content


def build_skill_docs(skills: List[Dict[str, str]]) -> str:
    """Build the skills section for injection into the system prompt.

    Returns a formatted string with all skill docs, or "" if none.
    """
    if not skills:
        return ""

    sections = ["=== Your Skills ===\n"]
    for skill in skills:
        header = f"### {skill['name']}"
        if skill['description']:
            header += f"\n_{skill['description']}_"
        sections.append(header)
        sections.append(skill['content'])

    return "\n\n".join(sections)

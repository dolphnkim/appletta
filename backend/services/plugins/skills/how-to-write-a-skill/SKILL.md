---
name: how-to-write-a-skill
description: How to create and register a new skill doc for yourself
---

Skills are markdown procedure docs that live in `backend/services/plugins/skills/`.
Each skill teaches you how to do a multi-step thing using your existing tools.
Skills show up here in your system prompt automatically — no restart needed.

## To create a new skill

1. Pick a short kebab-case name for it, e.g. `debug-backend` or `write-a-feature`.

2. Write the skill file:
   ```
   write_file(
     path="backend/services/plugins/skills/<your-skill-name>/SKILL.md",
     content="---\nname: your-skill-name\ndescription: one line about what this skill is for\n---\n\n# Body\n\nProcedure steps here..."
   )
   ```

3. Call `reload_skills` to confirm it loaded and see the full list of active skills.

4. The new skill will appear in your context on your **next** conversation turn.

## What makes a good skill

- **A clear trigger** — when should you use this skill? State it up front.
- **Concrete steps** — use your actual tool names with example arguments.
- **Decision points** — what do you do if a step fails or returns something unexpected?
- **Boundaries** — what does this skill *not* cover?

## To update or delete a skill

Update: `write_file` the same path with new content, then `reload_skills`.
Delete: `run_shell("rm -rf backend/services/plugins/skills/<skill-name>")`, then `reload_skills`.

"""GitHub tools — lets Kevin interact with his fork on GitHub.

Reads KEVIN_GITHUB_TOKEN and KEVIN_GITHUB_REPO from the .env file.
KEVIN_GITHUB_REPO should be in "owner/repo" format, e.g. "kevin-the-droid/persist".

Tools provided:
  github_create_pr      — open a pull request from a branch
  github_list_prs       — list open (or all) pull requests
  github_get_pr         — get status, comments, and review decisions on a PR
  github_create_issue   — file a bug or feature request
  github_list_issues    — browse open issues
"""

import os
from pathlib import Path
from typing import Any, Dict

# Load .env so the token is available even before the server does it
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent.parent.parent / ".env")


def _get_repo():
    """Return an authenticated github.Repository object, or raise with a clear message."""
    token = os.getenv("KEVIN_GITHUB_TOKEN")
    repo_name = os.getenv("KEVIN_GITHUB_REPO")

    if not token:
        raise ValueError("KEVIN_GITHUB_TOKEN is not set in .env")
    if not repo_name:
        raise ValueError("KEVIN_GITHUB_REPO is not set in .env")

    from github import Github
    gh = Github(token)
    return gh.get_repo(repo_name)


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "github_create_pr",
            "description": (
                "Open a pull request on Kevin's GitHub fork. "
                "The head branch is the branch you want to merge (e.g. 'kevin/my-feature'). "
                "The base branch is what it merges into (usually 'main'). "
                "Returns the PR number and URL."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "PR title"
                    },
                    "body": {
                        "type": "string",
                        "description": "PR description — explain what changed and why"
                    },
                    "head": {
                        "type": "string",
                        "description": "The branch to merge from, e.g. 'kevin/my-feature'"
                    },
                    "base": {
                        "type": "string",
                        "description": "The branch to merge into (default: 'main')",
                        "default": "main"
                    }
                },
                "required": ["title", "body", "head"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "github_list_prs",
            "description": (
                "List pull requests on Kevin's fork. "
                "By default returns open PRs. Set state to 'closed' or 'all' to see others. "
                "Returns PR number, title, author, branch, and URL for each."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "state": {
                        "type": "string",
                        "description": "Filter by state: 'open' (default), 'closed', or 'all'",
                        "default": "open"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max number of PRs to return (default: 10)",
                        "default": 10
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "github_get_pr",
            "description": (
                "Get full details on a specific pull request: status, merge state, "
                "review decisions, and comments. Use github_list_prs to find the PR number first."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pr_number": {
                        "type": "integer",
                        "description": "The PR number (from github_list_prs)"
                    }
                },
                "required": ["pr_number"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "github_create_issue",
            "description": (
                "File a new issue on Kevin's fork — use this to track bugs, ideas, or "
                "feature requests. Returns the issue number and URL."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Issue title"
                    },
                    "body": {
                        "type": "string",
                        "description": "Issue description — be specific about what's wrong or what's wanted"
                    },
                    "labels": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of label names to apply, e.g. ['bug', 'enhancement']"
                    }
                },
                "required": ["title", "body"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "github_list_issues",
            "description": (
                "List issues on Kevin's fork. Returns open issues by default. "
                "Each result includes issue number, title, labels, and URL."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "state": {
                        "type": "string",
                        "description": "Filter by state: 'open' (default), 'closed', or 'all'",
                        "default": "open"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max number of issues to return (default: 10)",
                        "default": 10
                    }
                },
                "required": []
            }
        }
    }
]


def execute(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    try:
        repo = _get_repo()
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"GitHub authentication failed: {e}"}

    try:
        if tool_name == "github_create_pr":
            pr = repo.create_pull(
                title=arguments["title"],
                body=arguments.get("body", ""),
                head=arguments["head"],
                base=arguments.get("base", "main"),
            )
            return {
                "success": True,
                "pr_number": pr.number,
                "url": pr.html_url,
                "state": pr.state,
            }

        elif tool_name == "github_list_prs":
            state = arguments.get("state", "open")
            limit = int(arguments.get("limit", 10))
            prs = list(repo.get_pulls(state=state)[:limit])
            return {
                "prs": [
                    {
                        "number": pr.number,
                        "title": pr.title,
                        "state": pr.state,
                        "author": pr.user.login,
                        "head": pr.head.ref,
                        "base": pr.base.ref,
                        "url": pr.html_url,
                        "created_at": pr.created_at.isoformat(),
                    }
                    for pr in prs
                ],
                "count": len(prs),
            }

        elif tool_name == "github_get_pr":
            pr = repo.get_pull(int(arguments["pr_number"]))
            reviews = [
                {
                    "reviewer": r.user.login,
                    "state": r.state,
                    "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
                }
                for r in pr.get_reviews()
            ]
            comments = [
                {
                    "author": c.user.login,
                    "body": c.body,
                    "created_at": c.created_at.isoformat(),
                }
                for c in pr.get_issue_comments()
            ]
            return {
                "number": pr.number,
                "title": pr.title,
                "state": pr.state,
                "mergeable": pr.mergeable,
                "merged": pr.merged,
                "author": pr.user.login,
                "head": pr.head.ref,
                "base": pr.base.ref,
                "url": pr.html_url,
                "body": pr.body,
                "reviews": reviews,
                "comments": comments,
                "created_at": pr.created_at.isoformat(),
            }

        elif tool_name == "github_create_issue":
            labels = arguments.get("labels", [])
            kwargs = {"title": arguments["title"], "body": arguments.get("body", "")}
            if labels:
                kwargs["labels"] = labels
            issue = repo.create_issue(**kwargs)
            return {
                "success": True,
                "issue_number": issue.number,
                "url": issue.html_url,
            }

        elif tool_name == "github_list_issues":
            state = arguments.get("state", "open")
            limit = int(arguments.get("limit", 10))
            issues = list(repo.get_issues(state=state)[:limit])
            # Filter out pull requests (GitHub API includes them in issues)
            issues = [i for i in issues if not i.pull_request]
            return {
                "issues": [
                    {
                        "number": i.number,
                        "title": i.title,
                        "state": i.state,
                        "author": i.user.login,
                        "labels": [l.name for l in i.labels],
                        "url": i.html_url,
                        "created_at": i.created_at.isoformat(),
                    }
                    for i in issues
                ],
                "count": len(issues),
            }

        else:
            return {"error": f"Unknown tool in github_tools: {tool_name}"}

    except Exception as e:
        return {"error": f"GitHub API error: {e}"}

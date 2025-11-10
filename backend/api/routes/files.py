/backend/
"""File browser API for selecting model/adapter paths

 

Allows UI to browse the filesystem and select directories containing MLX models

"""

 

import os

from pathlib import Path

from typing import List, Optional

 

from fastapi import APIRouter, HTTPException, Query

from pydantic import BaseModel

 

 

router = APIRouter(prefix="/api/v1/files", tags=["files"])

 

 

class FileItem(BaseModel):

    """Represents a file or directory in the browser"""

    name: str

    path: str

    is_directory: bool

    is_model: bool = False  # True if directory contains model files

    size: Optional[int] = None  # File size in bytes (None for directories)

 

 

class BrowseResponse(BaseModel):

    """Response from file browser"""

    current_path: str

    parent_path: Optional[str]

    items: List[FileItem]

 

 

def is_mlx_model_directory(path: Path) -> bool:

    """Check if directory contains MLX model files

 

    MLX models typically have:

    - config.json

    - .safetensors files

    - tokenizer files

    """

    if not path.is_dir():

        return False

 

    contents = set(f.name for f in path.iterdir())

 

    # Check for common MLX model files

    has_config = "config.json" in contents

    has_safetensors = any(f.endswith(".safetensors") for f in contents)

    has_tokenizer = any("tokenizer" in f.lower() for f in contents)

 

    return has_config or has_safetensors or has_tokenizer

 

 

@router.get("/browse", response_model=BrowseResponse)

async def browse_files(

    path: str = Query("/Users", description="Directory path to browse"),

    show_hidden: bool = Query(False, description="Show hidden files/folders"),

):

    """Browse filesystem for model selection

 

    Returns list of directories and files at the given path.

    Marks directories that appear to contain MLX models.

 

    Args:

        path: Directory to browse

        show_hidden: Whether to show hidden files (starting with .)

 

    Returns:

        List of files/directories with metadata

    """

    try:

        current_path = Path(path).expanduser().resolve()

    except Exception as e:

        raise HTTPException(400, f"Invalid path: {e}")

 

    if not current_path.exists():

        raise HTTPException(404, f"Path does not exist: {path}")

 

    if not current_path.is_dir():

        raise HTTPException(400, f"Path is not a directory: {path}")

 

    # Get parent directory (None if at root)

    parent_path = str(current_path.parent) if current_path.parent != current_path else None

 

    items = []

 

    try:

        for entry in sorted(current_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):

            # Skip hidden files unless requested

            if not show_hidden and entry.name.startswith('.'):

                continue

 

            # Skip system directories we shouldn't browse

            if entry.name in {'System', 'Library', 'private', 'dev', 'proc'}:

                continue

 

            try:

                is_dir = entry.is_dir()

                is_model = is_mlx_model_directory(entry) if is_dir else False

 

                item = FileItem(

                    name=entry.name,

                    path=str(entry),

                    is_directory=is_dir,

                    is_model=is_model,

                    size=entry.stat().st_size if not is_dir else None,

                )

                items.append(item)

            except PermissionError:

                # Skip files/directories we don't have permission to access

                continue

 

    except PermissionError:

        raise HTTPException(403, f"Permission denied: {path}")

 

    return BrowseResponse(

        current_path=str(current_path),

        parent_path=parent_path,

        items=items,

    )

 

 

@router.get("/validate-model")

async def validate_model_path(

    path: str = Query(..., description="Path to model directory"),

):

    """Validate that a path contains a valid MLX model

 

    Used before saving agent configuration to ensure model exists and is valid

 

    Returns:

        - is_valid: Whether path contains a valid model

        - message: Explanation if invalid

        - metadata: Model info (name, size, etc.) if valid

    """

    try:

        model_path = Path(path).expanduser().resolve()

    except Exception as e:

        return {

            "is_valid": False,

            "message": f"Invalid path: {e}",

        }

 

    if not model_path.exists():

        return {

            "is_valid": False,

            "message": "Path does not exist",

        }

 

    if not model_path.is_dir():

        return {

            "is_valid": False,

            "message": "Path is not a directory",

        }

 

    is_model = is_mlx_model_directory(model_path)

 

    if not is_model:

        return {

            "is_valid": False,

            "message": "Directory does not appear to contain a valid MLX model (missing config.json or .safetensors files)",

        }

 

    # Get model metadata

    # TODO: Parse config.json for model info

    try:

        size = sum(f.stat().st_size for f in model_path.rglob('*') if f.is_file())

        file_count = len(list(model_path.rglob('*')))

    except:

        size = None

        file_count = None

 

    return {

        "is_valid": True,

        "message": "Valid MLX model directory",

        "metadata": {

            "name": model_path.name,

            "path": str(model_path),

            "size_bytes": size,

            "file_count": file_count,

        }

    }

 

 

# TODO: Add endpoint for common model locations

@router.get("/suggested-paths")

async def get_suggested_model_paths():

    """Return common locations where MLX models are typically stored

 

    Helps users quickly navigate to their models directory

    """

    home = Path.home()

 

    suggested = [

        str(home / "Models"),

        str(home / ".cache/huggingface/hub"),

        str(home / "Downloads"),

        "/Users/Shared/Models",  # Common shared location on macOS

    ]

 

    # Filter to only paths that exist

    existing = [p for p in suggested if Path(p).exists()]

 

    return {

        "suggested_paths": existing

    }

 

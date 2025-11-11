"""API routes for RAG filesystem management"""

import os
import hashlib
from pathlib import Path
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.db.models.rag import RagFolder, RagFile, RagChunk
from backend.schemas.rag import (
    RagFolderCreate,
    RagFolderUpdate,
    RagFolderResponse,
    RagFileResponse,
)

router = APIRouter(prefix="/api/v1/rag", tags=["rag"])


# ============================================================================
# Folder Management
# ============================================================================

@router.post("/folders", response_model=RagFolderResponse)
async def attach_folder(
    folder_data: RagFolderCreate,
    db: Session = Depends(get_db)
):
    """Attach a filesystem folder for RAG

    Validates that the path exists and is a directory.
    """
    # Validate path exists
    folder_path = Path(folder_data.path).expanduser().resolve()
    if not folder_path.exists():
        raise HTTPException(404, f"Path does not exist: {folder_data.path}")

    if not folder_path.is_dir():
        raise HTTPException(400, f"Path is not a directory: {folder_data.path}")

    # Use folder name as display name if not provided
    name = folder_data.name or folder_path.name

    # Check if already attached
    existing = db.query(RagFolder).filter(
        RagFolder.agent_id == folder_data.agent_id,
        RagFolder.path == str(folder_path)
    ).first()

    if existing:
        raise HTTPException(409, f"Folder already attached: {folder_path}")

    # Create folder
    folder = RagFolder(
        agent_id=folder_data.agent_id,
        path=str(folder_path),
        name=name,
        max_files_open=folder_data.max_files_open,
        per_file_char_limit=folder_data.per_file_char_limit,
        source_instructions=folder_data.source_instructions,
    )

    db.add(folder)
    db.commit()
    db.refresh(folder)

    return folder.to_dict()


@router.get("/folders", response_model=List[RagFolderResponse])
async def list_folders(
    agent_id: UUID,
    db: Session = Depends(get_db)
):
    """List all attached folders for an agent"""
    folders = db.query(RagFolder).filter(
        RagFolder.agent_id == agent_id
    ).order_by(RagFolder.created_at.desc()).all()

    return [folder.to_dict() for folder in folders]


@router.get("/folders/{folder_id}", response_model=RagFolderResponse)
async def get_folder(
    folder_id: UUID,
    db: Session = Depends(get_db)
):
    """Get a specific folder"""
    folder = db.query(RagFolder).filter(RagFolder.id == folder_id).first()
    if not folder:
        raise HTTPException(404, f"Folder {folder_id} not found")

    return folder.to_dict()


@router.patch("/folders/{folder_id}", response_model=RagFolderResponse)
async def update_folder(
    folder_id: UUID,
    updates: RagFolderUpdate,
    db: Session = Depends(get_db)
):
    """Update folder settings (including source instructions)"""
    folder = db.query(RagFolder).filter(RagFolder.id == folder_id).first()
    if not folder:
        raise HTTPException(404, f"Folder {folder_id} not found")

    update_data = updates.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(folder, key, value)

    db.commit()
    db.refresh(folder)

    return folder.to_dict()


@router.delete("/folders/{folder_id}")
async def detach_folder(
    folder_id: UUID,
    db: Session = Depends(get_db)
):
    """Detach a folder (removes files and chunks)"""
    folder = db.query(RagFolder).filter(RagFolder.id == folder_id).first()
    if not folder:
        raise HTTPException(404, f"Folder {folder_id} not found")

    folder_name = folder.name
    db.delete(folder)
    db.commit()

    return {"message": f"Folder '{folder_name}' detached successfully"}


# ============================================================================
# File Management
# ============================================================================

@router.get("/folders/{folder_id}/files", response_model=List[RagFileResponse])
async def list_files(
    folder_id: UUID,
    db: Session = Depends(get_db)
):
    """List all files in a folder"""
    folder = db.query(RagFolder).filter(RagFolder.id == folder_id).first()
    if not folder:
        raise HTTPException(404, f"Folder {folder_id} not found")

    files = db.query(RagFile).filter(
        RagFile.folder_id == folder_id
    ).order_by(RagFile.filename).all()

    return [file.to_dict() for file in files]


@router.post("/folders/{folder_id}/scan")
async def scan_folder(
    folder_id: UUID,
    db: Session = Depends(get_db)
):
    """Scan folder and index new/changed files

    This discovers files in the folder and adds them to the database.
    Actual embedding/chunking happens in a separate background task.
    """
    folder = db.query(RagFolder).filter(RagFolder.id == folder_id).first()
    if not folder:
        raise HTTPException(404, f"Folder {folder_id} not found")

    folder_path = Path(folder.path)
    if not folder_path.exists():
        raise HTTPException(404, f"Folder path no longer exists: {folder.path}")

    # Scan for files
    discovered_files = []
    supported_extensions = {'.txt', '.md', '.json', '.py', '.js', '.ts', '.jsx', '.tsx', '.html', '.css'}

    for file_path in folder_path.rglob('*'):
        if file_path.is_file() and file_path.suffix.lower() in supported_extensions:
            try:
                # Calculate content hash
                with open(file_path, 'rb') as f:
                    content_hash = hashlib.sha256(f.read()).hexdigest()

                # Check if file already exists
                existing_file = db.query(RagFile).filter(
                    RagFile.folder_id == folder_id,
                    RagFile.path == str(file_path)
                ).first()

                if existing_file:
                    # Check if content changed
                    if existing_file.content_hash != content_hash:
                        # File changed - would trigger re-indexing
                        discovered_files.append({
                            "path": str(file_path),
                            "status": "changed",
                            "file_id": str(existing_file.id)
                        })
                else:
                    # New file - add to database
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()

                    new_file = RagFile(
                        folder_id=folder_id,
                        path=str(file_path),
                        filename=file_path.name,
                        extension=file_path.suffix,
                        size_bytes=file_path.stat().st_size,
                        raw_content=content,
                        content_hash=content_hash,
                    )

                    db.add(new_file)
                    discovered_files.append({
                        "path": str(file_path),
                        "status": "new",
                    })

            except Exception as e:
                # Skip files we can't read
                continue

    db.commit()

    return {
        "folder_id": str(folder_id),
        "discovered_files": len(discovered_files),
        "files": discovered_files,
        "message": f"Scanned folder, found {len(discovered_files)} new/changed files"
    }


@router.delete("/files/{file_id}")
async def delete_file(
    file_id: UUID,
    db: Session = Depends(get_db)
):
    """Remove a file from RAG (doesn't delete from filesystem)"""
    file = db.query(RagFile).filter(RagFile.id == file_id).first()
    if not file:
        raise HTTPException(404, f"File {file_id} not found")

    filename = file.filename
    db.delete(file)
    db.commit()

    return {"message": f"File '{filename}' removed from RAG"}

# Library imports
from pathlib import Path
from typing import Optional
import hashlib
import aiofiles
import aiofiles.os
import shutil

# Local imports
from smarta2a.file_stores.base_file_store import BaseFileStore

class LocalFileStore(BaseFileStore):
    """
    Local filesystem implementation that mimics cloud storage patterns
    - Stores files in task-specific directories
    - Uses content-addressable storage for deduplication
    - Generates file:// URIs for compatibility
    """
    
    def __init__(self, base_path: str = "./filestore"):
        self.base_path = Path(base_path).resolve()
        self.base_path.mkdir(parents=True, exist_ok=True)
    
    async def upload(self, content: bytes, task_id: str, filename: Optional[str] = None) -> str:
        # Create task directory if not exists
        task_dir = self.base_path / task_id
        await aiofiles.os.makedirs(task_dir, exist_ok=True)
        
        # Ensure content is bytes for hashing
        if isinstance(content, str):
            content = content.encode('utf-8')
        
        # Generate content hash for deduplication
        content_hash = hashlib.sha256(content).hexdigest()
        file_ext = Path(filename).suffix if filename else ""
        unique_name = f"{content_hash}{file_ext}"
        
        # Write file
        file_path = task_dir / unique_name
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(content)
            
        return f"file://{file_path}"


    async def download(self, uri: str) -> bytes:
        # Parse file:// URI
        path = Path(uri.replace("file://", ""))
        if not path.exists():
            raise FileNotFoundError(f"File not found at {uri}")
            
        async with aiofiles.open(path, "rb") as f:
            return await f.read()

    async def delete_for_task(self, task_id: str) -> None:
        task_dir = self.base_path / task_id
        if await aiofiles.os.path.exists(task_dir):
            await aiofiles.os.rmdir(task_dir)

    async def list_files(self, task_id: str) -> list[str]:
        task_dir = self.base_path / task_id
        if not await aiofiles.os.path.exists(task_dir):
            return []
            
        return [
            f"file://{file_path}"
            for file_path in task_dir.iterdir()
            if file_path.is_file()
        ]

    async def clear_all(self) -> None:
        """Clear entire storage (useful for testing)"""
        if await aiofiles.os.path.exists(self.base_path):
            shutil.rmtree(self.base_path)
        await aiofiles.os.makedirs(self.base_path, exist_ok=True)
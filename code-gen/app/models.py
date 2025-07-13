from pydantic import BaseModel, Field
from typing import List, Optional

class TDDInput(BaseModel):
    tdd_text: List[str] = Field(..., description="List of strings forming the Technical Design Document.")

class CodeGenerationResponse(BaseModel):
    message: str
    zip_download_url: Optional[str] = None
    # You might want to include the final TDD text or other metadata here too
    # final_tdd_text: Optional[List[str]] = None
    # generated_files_count: Optional[int] = None
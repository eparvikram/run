# main.py

import os
import shutil
import asyncio
from datetime import datetime
from typing import Annotated, Optional, Union, List, Dict, Literal # Kept common types for clarity, though some might be unused now
from pathlib import Path # Used for path manipulation, good practice

from fastapi import FastAPI, HTTPException, status, BackgroundTasks, Depends, Request, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse # JSONResponse is not directly used in this version, but good to keep
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from docx import Document # Explicitly needed for docx reading
import io # Needed for io.BytesIO when reading docx

import logging

# --- Configure logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Load environment variables at the top ---
load_dotenv()

# --- Retrieve API Keys (APP_API_KEY is still used by verify_api_key) ---
APP_API_KEY = os.getenv("APP_API_KEY")
# OPENAI_API_KEY is not directly used in main.py, so its retrieval removed here
# OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


# Corrected Import: Ensure these modules exist and are importable from your 'app' package
# and ensure `HumanMessage` is imported for use in initial_state if needed by LangGraph.
try:
    from app.models import TDDInput, CodeGenerationResponse # TDDInput is technically still imported but not used as a request body
    from app.services import CodeGenState, langgraph_app
    from langchain_core.messages import HumanMessage # Crucial for LangGraph initial state messages
    logger.info("Successfully imported LangGraph components from app.services and app.models.")
except ImportError as e:
    logger.error(f"Failed to import internal modules: {e}. Please ensure app/models.py and app/services.py exist and define the required components.")
    # In a production setup, you might want to re-raise the exception or halt app startup here.
    exit(1) # Exit if essential imports fail at startup


# --- FastAPI Application Instance ---
app = FastAPI(
    title="Code Generation Service",
    description="API to generate application code based on TDD from an uploaded DOCX file and return a downloadable zip.",
    version="1.0.0",
    openapi_tags=[
        {"name": "Code Generation", "description": "Endpoints for generating and downloading code."},
    ],
)

# --- CORS Configuration ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Dependency to validate API Key ---
# This function remains as is, as it's used by the download endpoint.
def verify_api_key(request: Request):
    api_key = request.headers.get("X-API-Key")
    
    if not APP_API_KEY:
        logger.warning("[CRITICAL] APP_API_KEY is not set in environment variables. API key validation cannot be performed effectively.")
    
    if APP_API_KEY and (not api_key or api_key != APP_API_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API Key",
            headers={"WWW-Authenticate": "X-API-Key"},
        )
    return api_key


# --- Temporary directory for generated zip files ---
# This needs to be consistent with app.services.py's output_dir and temp_zip_dir usage.
TEMP_ARTIFACTS_FOLDER = "temp_artifacts" 
os.makedirs(TEMP_ARTIFACTS_FOLDER, exist_ok=True)


# --- Helper Functions ---

def read_docx(file_content: bytes) -> str:
    """Reads content from a .docx file provided as bytes."""
    try:
        doc = Document(io.BytesIO(file_content))
        full_text = []
        for para in doc.paragraphs:
            full_text.append(para.text)
        return "\n".join(full_text)
    except Exception as e:
        logger.error(f"Error reading DOCX file: {e}")
        # Re-raise as HTTPException so FastAPI handles it correctly
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Could not process DOCX file: {e}")


def cleanup_generated_files(zip_path: str, artifact_sub_dir_path: str):
    """Cleans up the generated zip file and the entire request-specific artifact directory."""
    logger.info(f"Initiating cleanup for: {zip_path} and directory: {artifact_sub_dir_path}")
    try:
        if os.path.exists(zip_path):
            os.remove(zip_path)
            logger.info(f"Removed zip file: {zip_path}")
        else:
            logger.warning(f"Zip file not found for cleanup: {zip_path}. It might have been already cleaned or never created.")

        if os.path.exists(artifact_sub_dir_path):
            shutil.rmtree(artifact_sub_dir_path, ignore_errors=True) # Use ignore_errors=True for robustness
            logger.info(f"Removed artifact directory: {artifact_sub_dir_path}")
        else:
            logger.warning(f"Artifact directory not found for cleanup: {artifact_sub_dir_path}. It might have been already cleaned.")
    except Exception as e:
        logger.error(f"[ERROR] Error during cleanup of {zip_path} or {artifact_sub_dir_path}: {e}", exc_info=True)


# --- FastAPI Endpoints ---

@app.get("/", summary="Root endpoint")
async def read_root():
    return {"message": "Welcome to the Code Generation Service! Visit /docs for API documentation."}


@app.post(
    "/generate-code-hld",
    response_model=CodeGenerationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Generate application code from an uploaded DOCX TDD and provide a download link."
)
async def generate_code_endpoint(
    background_tasks: BackgroundTasks, # Moved this parameter to the beginning
    tdd_file: UploadFile = File(..., description="Upload a .docx file containing the TDD."),
    # api_key: Annotated[str, Depends(verify_api_key)] # Re-enable if API key is desired for this endpoint
):
    """
    Receives a DOCX TDD file, extracts its content, triggers LangGraph for code generation,
    and returns a URL to download the generated ZIP file when ready.
    The actual code generation and zipping is performed as a background task.
    """
    logger.info(f"Received request for /generate-code-hld with file: {tdd_file.filename}")

    # 1. Validate file type
    if not tdd_file.filename.lower().endswith(".docx"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unsupported file type. Only .docx files are allowed for TDD upload."
        )

    # 2. Extract content from DOCX
    try:
        file_content_bytes = await tdd_file.read()
        extracted_tdd_content = read_docx(file_content_bytes)
        logger.info(f"Successfully extracted text from DOCX (first 100 chars): {extracted_tdd_content[:100]}...")
    except HTTPException: # Re-raise if read_docx already raised one
        raise
    except Exception as e:
        logger.error(f"Failed to read or process DOCX file: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to read DOCX file: {e}")


    # 3. Define unique output directories for this request to avoid conflicts
    request_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
    
    # Each request gets its own unique sub-directory within TEMP_ARTIFACTS_FOLDER
    # This sub-directory will contain both the 'generated_code' and 'final_zip' folders for this specific request.
    request_specific_artifact_sub_dir = f"req_{request_id}"
    full_artifact_dir_path = Path(TEMP_ARTIFACTS_FOLDER) / request_specific_artifact_sub_dir
    
    # Define paths for LangGraph's use within this unique artifact directory
    generated_code_output_path = full_artifact_dir_path / "generated_code"
    final_zip_storage_path = full_artifact_dir_path / "final_zip" # This is where the final .zip will be placed

    # Ensure these directories exist before LangGraph starts
    generated_code_output_path.mkdir(parents=True, exist_ok=True)
    final_zip_storage_path.mkdir(parents=True, exist_ok=True)


    # 4. Initialize LangGraph state with these unique directories and TDD content
    initial_state = CodeGenState(
        tdd_text=[extracted_tdd_content], # Pass raw TDD text to LangGraph
        output_dir=str(generated_code_output_path), # Path where individual code files will be saved
        temp_zip_dir=str(final_zip_storage_path),   # Path where the final zip file will be saved
        messages=[HumanMessage(content=extracted_tdd_content)] # Initial message for LLM context
    )
    
    # 5. Run the LangGraph workflow as a background task.
    # The LangGraph app uses .ainvoke and needs to be awaited directly.
    # We define an async wrapper function to run it in the background.
    async def run_workflow_and_handle_completion():
        try:
            logger.info(f"Starting LangGraph workflow for request {request_id} in background.")
            # Execute the LangGraph workflow. It will handle file generation and zipping internally.
            final_state_result_dict = await langgraph_app.ainvoke(initial_state)
            
            # The LangGraph workflow in services.py is expected to update the state with 'zip_file_path'
            # when it successfully creates the zip.
            final_state_model = CodeGenState(**final_state_result_dict) # Re-instantiate for type safety

            if final_state_model.zip_file_path and Path(final_state_model.zip_file_path).exists():
                logger.info(f"LangGraph workflow completed and zip generated for request {request_id}. Zip: {final_state_model.zip_file_path}")
            else:
                logger.error(f"LangGraph workflow completed, but no valid zip_file_path found in final state for request {request_id}.")

        except Exception as e:
            logger.error(f"[ERROR] LangGraph workflow failed for request {request_id}: {e}", exc_info=True)
            # In a more advanced system, you might persist the error status for this request_id
            # so the /download-zip endpoint can return a more specific error than 404.

    background_tasks.add_task(run_workflow_and_handle_completion)

    # 6. Return the URL for the frontend to poll for download.
    # The URL now refers to the request-specific artifact sub-directory.
    zip_download_url = f"/download-zip/{request_specific_artifact_sub_dir}"
    
    logger.info(f"Code generation initiated. Returning download URL: {zip_download_url}")
    return CodeGenerationResponse(
        message="Code generation started. Please use the provided URL to download the zip file.",
        zip_download_url=zip_download_url
    )


@app.get(
    "/download-zip/{artifact_sub_dir}",
    summary="Download the generated code zip file for a specific request.",
    response_class=FileResponse
)
async def download_zip_file(
    artifact_sub_dir: str, # This is the unique folder inside TEMP_ARTIFACTS_FOLDER for the request
    background_tasks: BackgroundTasks, # To add cleanup task
    api_key: Annotated[str, Depends(verify_api_key)] # Apply API key dependency (adjust if no API key is desired)
):
    """
    Endpoint to download the generated zip file.
    The frontend will poll this endpoint using the URL obtained from /generate-code-hld.
    """
    # Reconstruct the full path to the request-specific final_zip folder
    # where the zip file is expected to be placed by the background task.
    full_artifact_dir_path = Path(TEMP_ARTIFACTS_FOLDER) / artifact_sub_dir
    final_zip_folder = full_artifact_dir_path / "final_zip"
    
    zip_file_to_serve: Optional[Path] = None

    # Scan the specific `final_zip_folder` for a .zip file
    if final_zip_folder.is_dir():
        zip_files_in_dir = [f for f in os.listdir(final_zip_folder) if f.endswith(".zip")]
        if zip_files_in_dir:
            # Assuming only one zip file per request's unique zip folder
            zip_file_to_serve = final_zip_folder / zip_files_in_dir[0]

    if zip_file_to_serve and zip_file_to_serve.is_file():
        logger.info(f"Serving zip file: {zip_file_to_serve}")
        # Add the cleanup task to be performed after the file is sent
        # cleanup_generated_files will remove the zip file AND the entire request_specific_artifact_sub_dir
        background_tasks.add_task(cleanup_generated_files, str(zip_file_to_serve), str(full_artifact_dir_path))

        return FileResponse(
            path=zip_file_to_serve,
            media_type="application/zip",
            filename=zip_file_to_serve.name, # Suggests the actual filename (e.g., generated_code_req_XYZ.zip)
            background=background_tasks
        )
    else:
        logger.warning(f"Zip file not found in {final_zip_folder} or not yet ready for {artifact_sub_dir}.")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Code generation in progress or failed. Zip file not yet available. Please wait and retry."
        )

@app.get("/health", summary="Health check endpoint")
async def health_check():
    """Simple health check to verify API is running."""
    return {"status": "ok", "message": "API is running"}

@app.on_event("startup")
async def startup_event():
    logger.info(f"FastAPI app starting up. Ensuring TEMP_ARTIFACTS_FOLDER '{TEMP_ARTIFACTS_FOLDER}' exists.")
    Path(TEMP_ARTIFACTS_FOLDER).mkdir(parents=True, exist_ok=True)
    # Optional: Clear old temporary files on startup (use with caution in production)
    # try:
    #     shutil.rmtree(TEMP_ARTIFACTS_FOLDER)
    #     Path(TEMP_ARTIFACTS_FOLDER).mkdir(parents=True, exist_ok=True)
    #     logger.info(f"Cleaned up any old temporary files in '{TEMP_ARTIFACTS_FOLDER}' on startup.")
    # except Exception as e:
    #     logger.warning(f"Failed to clean up old temp artifacts on startup: {e}")

@app.on_event("shutdown")
def shutdown_event():
    logger.info(f"Shutting down API. Attempting to clean up '{TEMP_ARTIFACTS_FOLDER}'...")
    if Path(TEMP_ARTIFACTS_FOLDER).exists():
        try:
            shutil.rmtree(TEMP_ARTIFACTS_FOLDER, ignore_errors=True)
            logger.info(f"Temporary directories under '{TEMP_ARTIFACTS_FOLDER}' cleaned.")
        except Exception as e:
            logger.error(f"[ERROR] Failed to clean up '{TEMP_ARTIFACTS_FOLDER}' during shutdown: {e}")

# To run this FastAPI application:
# uvicorn main:app --host 0.0.0.0 --port 8000 --reload (from the project root directory)
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
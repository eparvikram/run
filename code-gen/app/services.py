import os
import json
import operator
import datetime
import shutil
import zipfile
from typing import Optional, Dict, List, Annotated

from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI, AzureChatOpenAI # Import both for conditional use
from langgraph.graph import StateGraph, END
from dotenv import load_dotenv


from app.utils import parse_code_blocks # Import your utility function

# --- Load environment variables ---
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")



class CodeGenState(BaseModel):
    # Accumulates messages throughout the graph
    tdd_text: Annotated[List[str], operator.add] = Field(default_factory=list)

    # Core framework/language/database detection (added these back based on your class definition)
    language: Optional[str] = None
    frontend: Optional[str] = None
    backend: Optional[str] = None
    database: Optional[str] = None
    is_valid_combination: Optional[bool] = None
    frontend_framework: Optional[str] = None

    # Extracted design elements (added these back)
    table_schemas: Optional[Dict[str, List[str]]] = None
    customer_ui_components: Optional[List[str]] = None
    api_endpoints: Optional[List[Dict[str, str]]] = None
    form_input_schemas: Optional[Dict[str, Dict]] = None

    # Generated code content (raw LLM output) (added these back)
    frontend_code: Optional[str] = None
    backend_code: Optional[str] = None
    sql_code: Optional[str] = None

    # Structured parsed code files (not used directly in current write_code_to_files but good for debugging)
    frontend_code_files: Optional[List[Dict[str, str]]] = None
    backend_code_files: Optional[List[Dict[str, str]]] = None
    sql_code_files: Optional[List[Dict[str, str]]] = None

# --- LLM Wrapper Function (used by LangGraph nodes) ---
#def ask_llm(prompt: str) -> str:
#    # Check if Azure OpenAI settings are available and prioritize them
#    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
#    azure_api_key = os.getenv("AZURE_OPENAI_API_KEY")
#    azure_api_version = os.getenv("AZURE_OPENAI_API_VERSION")
#    azure_deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
    
#    llm = None
#    if all([azure_endpoint, azure_api_key, azure_api_version, azure_deployment_name]):
#        print("[LLM Wrapper] Using Azure OpenAI...")
#        try:
#            llm = AzureChatOpenAI(
#                azure_endpoint=azure_endpoint,
#                api_key=azure_api_key,
#                api_version=azure_api_version,
#                azure_deployment=azure_deployment_name,
#                model_name="gpt-4o", # The underlying model name
#                temperature=0.2
#        except Exception as e:
#            print(f"[ERROR] Failed to initialize AzureChatOpenAI: {e}")
#            llm = None # Ensure llm is None if init fails
    
#    # Fallback to standard OpenAI if Azure not configured or failed to initialize
#    if llm is None:
#        openai_api_key = os.getenv("OPENAI_API_KEY")
#        if not openai_api_key:
#            print("[ERROR] Neither Azure OpenAI nor standard OPENAI_API_KEY is set in environment variables.")
#            return "ERROR: OpenAI API key not configured."
        
#        print("[LLM Wrapper] Using Standard OpenAI...")
#        llm = ChatOpenAI(model_name="gpt-4o", temperature=0.2, api_key=openai_api_key)

#    try:
#        response = llm.invoke(prompt)
#        return response.content.strip()
#    except Exception as e:
#        print(f"[ERROR] LLM invocation failed: {e}")
#        return f"ERROR: LLM call failed: {e}"

# --- LLM Wrapper ---
def ask_llm(prompt: str) -> str:
    if not OPENAI_API_KEY:
        print("[ERROR] OPENAI_API_KEY is not set in environment variables.")
        return "ERROR: OpenAI API key not configured."
    llm = ChatOpenAI(model_name="gpt-4o", temperature=0.2, api_key=OPENAI_API_KEY)
    try:
        response = llm.invoke(prompt)
        return response.content.strip()
    except Exception as e:
        print(f"[ERROR] LLM invocation failed: {e}")
        return f"ERROR: LLM call failed: {e}"


# --- Node Definitions ---
def start_node(state: CodeGenState) -> dict:
    print("[LangGraph: Start Node]")
    
    # Define the temporary zip directory explicitly
    TEMP_ZIP_FOLDER = 'temp_zips_api' 

    # Ensure clean slate for output and zip directories
    shutil.rmtree('generated_code', ignore_errors=True) # Assuming 'generated_code' is your main output dir
    shutil.rmtree(TEMP_ZIP_FOLDER, ignore_errors=True) # Clean up previous temp zips

    os.makedirs('generated_code', exist_ok=True) # Recreate main output dir
    os.makedirs(TEMP_ZIP_FOLDER, exist_ok=True) # Ensure the temp zip directory exists

    # You might want to update the CodeGenState to store these paths if they are used by other nodes
    # For now, just ensuring creation.
    # state.output_dir = 'generated_code' # Assuming you'd want to store this
    # state.temp_zip_dir = TEMP_ZIP_FOLDER # And this
    
    return {"tdd_text": state.tdd_text}


def detect_language(state: CodeGenState) -> dict:
    print("Executing DetectLanguage Node")
    current_tdd_text = "\n".join(state.tdd_text)
    prompt = f"""
You are a backend language classifier.
Detect the most suitable backend programming language from the TDD.
Only return one of: Python, Java, Node.js, Go, Rust. No explanation.

### TDD ###
{current_tdd_text}
"""
    result = ask_llm(prompt)
    return {
        "language": result if result else "Python",
        "tdd_text": [f"Language detection result: {result or 'Python'}"]
    }

def extract_customer_ui_and_form_details(state: CodeGenState) -> dict:
    """
    Identifies distinct UI components specifically related to the customer portal
    and extracts input field details for forms mentioned.
    """
    print("Executing ExtractCustomerUIAndFormDetails Node")
    current_tdd_text = "\n".join(state.tdd_text)

    prompt = f"""
You are an intelligent frontend architect assistant.

From the following Technical Design Document (TDD), extract all UI components
that customers interact with. For example: Registration form, Login form, Loan form, Dashboard.

Infer components like:
- CustomerRegistrationForm
- CustomerLoginForm
- LoanApplicationForm
- StatusTrackingDashboard

Return only the list in JSON: {{ "customer_ui_components": [...] }}.
No markdown, no prose.

TDD:
{current_tdd_text}
"""
    result = ask_llm(prompt)

    print("🔍 Raw Customer UI Components LLM Output:", result)

    # Parse the result
    customer_ui_components = []
    try:
        parsed = json.loads(result)
        if "customer_ui_components" in parsed:
            customer_ui_components = parsed["customer_ui_components"]
    except Exception as e:
        print("[ERROR] Failed to parse customer UI component list from LLM:", e)

    new_tdd_entry = f"Extracted customer UI components: {customer_ui_components}"
    updated_tdd_text = (state.tdd_text if state.tdd_text else []) + [new_tdd_entry]

    return {
        "customer_ui_components": customer_ui_components,
        "tdd_text": updated_tdd_text
    }


def generate_frontend_code(state: CodeGenState) -> dict:
    print("[GenerateFrontendCode Node]")
    prompt = f"""
You are a professional AI full-stack code generator.
Generate {state.frontend_framework} form components for:
{state.customer_ui_components}
Infer fields from the form name. Generate:
1. Component logic (React: JSX or Angular: TS)
2. Form HTML/JSX
3. Basic CSS
Use kebab-case filenames. One block per file. No explanation. No markdown.
"""
    code = ask_llm(prompt)
    return {
        "frontend_code": code
    }

def generate_requirements_txt(output_dir: str, language: Optional[str], backend: Optional[str]):
    """
    Generates a requirements.txt file with necessary libraries based on detected tech stack.
    """
    requirements_path = os.path.join(output_dir, "requirements.txt")
    base_requirements = {
        "pydantic>=2.0.0",
        "langchain-openai>=0.1.0",
        "langgraph>=0.0.60",
        "python-dotenv>=1.0.0",
    }

    if language == "Python":
        if backend == "FastAPI":
            base_requirements.add("fastapi")
            base_requirements.add("uvicorn[standard]")
            base_requirements.add("python-multipart")
        elif backend == "Flask":
            base_requirements.add("flask")
        elif backend == "Django":
            base_requirements.add("django")
    elif language == "Node.js":
        # For Node.js, we'd typically generate package.json, not requirements.txt
        # But for Python-centric LangGraph, we'll list common Python tools
        pass # Add node-specific package.json generation logic if needed

    requirements_content = "\n".join(sorted(list(base_requirements)))
    
    try:
        with open(requirements_path, "w") as f:
            f.write(requirements_content.strip())
        print(f"📄 Generated {requirements_path}")
    except Exception as e:
        print(f"[ERROR] Could not write requirements.txt: {e}")


def write_code_to_files(state: CodeGenState) -> dict:
    """
    Writes the generated frontend, backend, and SQL code to a structured folder system.
    Also, creates a requirements.txt file (though not implemented in this snippet).
    """
    print("\n💾 Executing WriteCodeToFiles Node...")

    output_base_dir = "generated_code"
    os.makedirs(output_base_dir, exist_ok=True)

    # --- Write Frontend Code ---
    if state.frontend_code and state.frontend:
        frontend_base_dir = os.path.join(output_base_dir, f"frontend_{state.frontend.lower()}")
        
        # Create the base frontend directory
        os.makedirs(frontend_base_dir, exist_ok=True)

        # Re-parse frontend code with component names and framework for best filename inference
        frontend_files = parse_code_blocks(state.frontend_code, state.customer_ui_components, state.frontend_framework)
        
        if not frontend_files and state.frontend_code.strip():
            print(f"[WARNING] Could not parse individual {state.frontend} code blocks. Saving as a single file.")
            with open(os.path.join(frontend_base_dir, "frontend_output.txt"), "w") as f:
                f.write(state.frontend_code)
        else:
            for file_data in frontend_files:
                filename = file_data["filename"]
                filepath = ""

                if state.frontend == "Angular":
                    # Angular CLI typical structure:
                    # frontend_angular/
                    #   src/
                    #     app/
                    #       app.module.ts
                    #       app.component.ts
                    #       app.component.html
                    #       app.component.css
                    #       customer-registration-form/
                    #         customer-registration-form.component.ts
                    #         customer-registration-form.component.html
                    #         customer-registration-form.component.css
                    #     main.ts
                    #     styles.css
                    #   index.html
                    
                    if filename.startswith("app.module.ts") or \
                       filename.startswith("app.component.ts") or \
                       filename.startswith("app.component.html") or \
                       filename.startswith("app.component.css"):
                        # These go directly into src/app
                        filepath = os.path.join(frontend_base_dir, "src", "app", filename)
                    elif filename.startswith("main.ts") or \
                         filename.startswith("styles.css"):
                        # These go directly into src/
                        filepath = os.path.join(frontend_base_dir, "src", filename)
                    elif filename.startswith("index.html"):
                        # index.html goes to the root of the frontend folder
                        filepath = os.path.join(frontend_base_dir, filename)
                    else:
                        # Assume it's a component, create a subfolder for it
                        # e.g., customer-registration-form.component.ts -> src/app/customer-registration-form/customer-registration-form.component.ts
                        component_folder_name = filename.split('.')[0] # e.g., "customer-registration-form"
                        component_dir = os.path.join(frontend_base_dir, "src", "app", component_folder_name)
                        filepath = os.path.join(component_dir, filename)
                
                elif state.frontend == "React":
                    # React typically:
                    # frontend_react/
                    #   public/
                    #     index.html
                    #   src/
                    #     index.js (or main.jsx)
                    #     App.jsx
                    #     index.css (or App.css)
                    #     components/
                    #       CustomerRegistrationForm.jsx
                    #       CustomerRegistrationForm.css
                    
                    if filename.startswith("index.html"):
                        filepath = os.path.join(frontend_base_dir, "public", filename)
                    elif filename.startswith("App.") or filename.startswith("index.") or filename.startswith("main."):
                        filepath = os.path.join(frontend_base_dir, "src", filename)
                    else:
                        # Assume it's a component
                        component_dir = os.path.join(frontend_base_dir, "src", "components")
                        filepath = os.path.join(component_dir, filename)

                else: # Fallback for other frameworks or if detection fails
                    filepath = os.path.join(frontend_base_dir, filename) # Place directly in the base dir for now

                try:
                    # Ensure the directory for the file exists
                    os.makedirs(os.path.dirname(filepath), exist_ok=True)
                    with open(filepath, "w") as f:
                        f.write(file_data["code"])
                    print(f"    Frontend: Wrote {filepath}")
                except Exception as e:
                    print(f"[ERROR] Could not write frontend file {filepath}: {e}")
    else:
        print("    No frontend code to write.")

    # --- Write Backend Code ---
    if state.backend_code and state.language and state.backend:
        backend_root_dir = os.path.join(output_base_dir, f"backend_{state.language.lower()}_{state.backend.lower().replace('.', '_')}")
        
        # Determine specific project/app structure based on backend framework
        if state.backend == "Django":
            django_project_name = "loan_app_project"
            django_app_name = "api" # Or a more descriptive name like 'loans'
            backend_app_dir = os.path.join(backend_root_dir, django_project_name, django_app_name)
            os.makedirs(backend_app_dir, exist_ok=True)
            
            target_dir_for_generated_files = backend_app_dir
        elif state.backend == "FastAPI":
            os.makedirs(backend_root_dir, exist_ok=True)
            target_dir_for_generated_files = backend_root_dir
        elif state.backend == "Flask":
            os.makedirs(backend_root_dir, exist_ok=True)
            target_dir_for_generated_files = backend_root_dir
        elif state.backend == "Express.js":
            os.makedirs(backend_root_dir, exist_ok=True)
            target_dir_for_generated_files = backend_root_dir
        else: # Default or other backend
            os.makedirs(backend_root_dir, exist_ok=True)
            target_dir_for_generated_files = backend_root_dir

        # Write generated backend code (models.py, views.py, serializers.py, urls.py for the app)
        backend_files = parse_code_blocks(state.backend_code) # No need for component names here
        if not backend_files and state.backend_code.strip():
            print("[WARNING] Could not parse individual backend code blocks. Saving as a single file.")
            with open(os.path.join(target_dir_for_generated_files, "backend_api.txt"), "w") as f:
                f.write(state.backend_code)
        else:
            for file_data in backend_files:
                filepath = os.path.join(target_dir_for_generated_files, file_data["filename"])
                try:
                    os.makedirs(os.path.dirname(filepath), exist_ok=True)
                    with open(filepath, "w") as f:
                        f.write(file_data["code"])
                    print(f"    Backend: Wrote {filepath}")
                except Exception as e:
                    print(f"[ERROR] Could not write backend file {filepath}: {e}")
    else:
        print("    No backend code to write.")

    # --- Write SQL Code ---
    if state.sql_code:
        db_dir = os.path.join(output_base_dir, "database")
        os.makedirs(db_dir, exist_ok=True)
        sql_filepath = os.path.join(db_dir, "schema.sql")
        try:
            with open(sql_filepath, "w") as f:
                f.write(state.sql_code)
            print(f"   SQL: Wrote {sql_filepath}")
        except Exception as e:
            print(f"[ERROR] Could not write SQL file {sql_filepath}: {e}")
    else:
        print("   No SQL code to write.")

    print("💾 Finished writing files.")
    return {"tdd_text": ["Files written to disk."]}

def detect_frontend(state: CodeGenState) -> dict:
    print("[DetectFrontend Node]")
    tdd = "\n".join(state.tdd_text)
    prompt = f"""
You are a frontend framework detector.
Detect the main frontend framework from this technical design document.
Only return one of: React, Angular, Vue, Svelte, HTML/CSS/JS Default. No explanation.
### TDD ###
{tdd}
"""
    detected = ask_llm(prompt)
    return {
        "frontend": detected,
        "frontend_framework": detected,
        "tdd_text": state.tdd_text + [f"Frontend detected: {detected}"]
    }

def zip_generated_code(state: CodeGenState) -> dict:
    """
    Zips the entire 'generated_code' directory into a .zip archive.
    Returns the path to the created zip file.
    """
    print("\n📦 Executing ZipGeneratedCode Node...")

    output_base_dir = "generated_code"
    zip_base_name = "generated_code"  # without .zip extension
    zip_file_path = os.path.abspath(f"{zip_base_name}.zip")

    try:
        if not os.path.exists(output_base_dir):
            raise FileNotFoundError(f"Directory '{output_base_dir}' does not exist.")

        # Create the zip archive
        shutil.make_archive(base_name=zip_base_name, format='zip', root_dir=output_base_dir)

        print(f"✅ Successfully created zip file: {zip_file_path}")
        return {
            "zip_file_path": zip_file_path,
            "tdd_text": [f"Zip archive created: {zip_file_path}"]
        }

    except Exception as e:
        print(f"❌ Error creating zip file: {e}")
        return {
            "zip_file_path": None,
            "tdd_text": [f"Failed to create zip archive: {e}"]
        }
def route_after_generation(state: CodeGenState) -> str:
    # Check for frontend code: requires frontend_code AND frontend_framework
    frontend_generated = state.frontend_code is not None and state.frontend_framework is not None
    
    # Check for backend code: requires backend_code AND language AND backend
    backend_generated = state.backend_code is not None and state.language is not None and state.backend is not None
    
    # Check for SQL code: requires sql_code AND database
    sql_generated = state.sql_code is not None and state.database is not None

    if frontend_generated or backend_generated or sql_generated:
        print("[INFO] At least one type of code was generated. Proceeding to write files.")
        return "WRITE_FILES"
    else:
        print("[WARNING] No code was generated for any layer. Ending workflow.")
        return "END"

def check_all_generated(state: CodeGenState) -> dict:
    print("--- ENTERING check_all_generated (Synchronization Point) ---")
    # This node just passes the state through. Its purpose is to ensure
    # all upstream generation nodes (frontend, backend, sql) have completed
    # and written their output to the state before WriteCodeToFiles is called.
    
    # You could add logging here to verify what's in the state if needed:
    # print(f"  Frontend code generated: {'Yes' if state.frontend_code else 'No'}")
    # print(f"  Backend code generated: {'Yes' if state.backend_code else 'No'}")
    # print(f"  SQL code generated: {'Yes' if state.sql_code else 'No'}")

    print("--- EXITING check_all_generated ---")
    return {"tdd_text": ["All generation tasks checked for completion."]} # Return only new message

def trigger_all_generators(state: CodeGenState) -> dict:
    print("✨ Dispatching all code generators in parallel...")
    # This node just serves as a fan-out point. No state change needed here.
    # It ensures all generation nodes are triggered simultaneously after validation.
    return {"tdd_text": ["Initiating parallel code generation."]} # Return only new message

def detect_frontend(state: CodeGenState) -> dict:
    print("[DetectFrontend Node]")
    tdd = "\n".join(state.tdd_text)
    prompt = f"""
You are a frontend framework detector.
Detect the main frontend framework from this technical design document.
Only return one of: React, Angular, Vue, Svelte, HTML/CSS/JS Default. No explanation.
### TDD ###
{tdd}
"""
    detected = ask_llm(prompt)
    return {
        "frontend": detected,
        "frontend_framework": detected,
        "tdd_text": state.tdd_text + [f"Frontend detected: {detected}"]
    }

def detect_database(state: CodeGenState) -> dict:
    """
    Detects the SQL database type from the TDD.
    """
    print("🌐 Executing DetectDatabase Node")
    current_tdd_text = "\n".join(state.tdd_text)

    prompt = f"""
You are a database system detector.
From the following Technical Design Document (TDD), identify the specific SQL database system mentioned.

If a SQL database is explicitly mentioned, return its name (e.g., PostgreSQL, MySQL, SQL Server, Oracle, SQLite).
If no specific SQL database is mentioned but a generic 'SQL database' is implied, return 'Generic SQL'.
If no database is mentioned or it's a NoSQL database, return 'None'.

Only return the database name or 'Generic SQL' or 'None'. No explanation.

TDD:
{current_tdd_text}
"""

    result = ask_llm(prompt)
    database = result.strip()
    print(f"📊 Detected Database: {database}")

    return {
        "database": database,
        "tdd_text": [f"Database detection result: {database}"]
    }

def detect_backend(state: CodeGenState) -> dict:
    print("Executing DetectBackend Node")
    current_tdd_text = "\n".join(state.tdd_text)
    prompt = f"""
You are a backend framework detector.
Detect the main backend framework used from this technical design document.
**CRITICAL: You MUST return one and only one of the following options: FastAPI, SpringBoot, Express.js, Flask, Django.**
Do NOT return 'None' or any other value. If unsure, make your best guess from the list. No explanation.

### TDD ###
{current_tdd_text}
"""
    result = ask_llm(prompt)
    
    # Ensure result is one of the allowed, even if LLM gives something else
    allowed_backends = {"FastAPI", "SpringBoot", "Express.js", "Flask", "Django"}
    if result not in allowed_backends:
        # Fallback to a default if LLM deviates significantly, or try to find a keyword
        if "django" in current_tdd_text.lower():
            result = "Django"
        elif "flask" in current_tdd_text.lower():
            result = "Flask"
        elif "fastapi" in current_tdd_text.lower():
            result = "FastAPI"
        elif "express" in current_tdd_text.lower():
            result = "Express.js"
        elif "spring" in current_tdd_text.lower():
            result = "SpringBoot"
        else:
            result = "FastAPI" # Default if no strong signal

    return {
        "backend": result,
        "tdd_text": [f"Backend detection result: {result}"]
    }

def extract_table_schema(state: CodeGenState) -> dict:
    print("Executing ExtractTableSchema Node")
    current_tdd_text = "\n".join(state.tdd_text)
    prompt = f"""
You are a database design assistant.

From the following Technical Design Document (TDD), extract all table names and their fields.

Return your answer as a **valid JSON object**, where keys are table names and values are arrays of column names.

No explanation. No markdown.

### TDD ###
{current_tdd_text}
"""
    result = ask_llm(prompt)

    try:
        table_schema_dict = json.loads(result)
        # Ensure the values are lists of strings, not just strings
        for key, value in table_schema_dict.items():
            if not isinstance(value, list):
                table_schema_dict[key] = [str(value)] # Convert to list if not already
            else:
                table_schema_dict[key] = [str(item) for item in value] # Ensure elements are strings
    except json.JSONDecodeError:
        print(f"[ERROR] Invalid JSON from LLM: {result}. Falling back to empty dict.")
        table_schema_dict = {}
    except Exception as e:
        print(f"[ERROR] An unexpected error occurred during JSON processing: {e}. Falling back to empty dict.")
        table_schema_dict = {}

    return {
        "table_schemas": table_schema_dict,
        "tdd_text": [f"Table schema extraction result: {json.dumps(table_schema_dict)}"]
    }


def extract_api_endpoints(state: CodeGenState) -> dict:
    """
    Extracts API endpoints (method, path, description) from the TDD.
    """
    print("🚦 Executing ExtractApiEndpoints Node")

    current_tdd_text = "\n".join(state.tdd_text)

    prompt = f"""
You are an API endpoint extraction specialist.
Your task is to meticulously parse **Section 3.3 API Design** from the provided Technical Design Document (TDD).

For each API endpoint listed, extract the following information:
1.  **Method:** The HTTP method (e.g., POST, GET, PUT, DELETE).
2.  **Path:** The URL path (e.g., /api/auth/register, /api/loans/:id).
3.  **Description:** A brief explanation of the endpoint's purpose.

**Strict Output Format:**
Return your answer as a **valid JSON list of objects**. Each object in the list MUST have the following keys and string values:
* "method": (e.g., "POST")
* "path": (e.g., "/api/auth/register")
* "description": (e.g., "User Registration")

**DO NOT include any explanation, markdown, or additional text outside the JSON array.**
**CRITICAL: DO NOT wrap the JSON in markdown code fences (```json ... ```).**

### TDD ###
{current_tdd_text}
"""

    result = ask_llm(prompt)
    print("🔍 Raw API Extraction Output:", result)

    if result.startswith("```json") and result.endswith("```"):
        result = result[len("```json"): -len("```")].strip()

    api_list = []
    try:
        parsed_result = json.loads(result)
        if isinstance(parsed_result, list):
            for item in parsed_result:
                if isinstance(item, dict) and all(k in item for k in ["method", "path", "description"]):
                    api_list.append({
                        "method": str(item["method"]).strip(),
                        "path": str(item["path"]).strip(),
                        "description": str(item["description"]).strip()
                    })
                else:
                    print(f"[WARNING] Skipping malformed API endpoint item (missing keys or not dict): {item}")
            if not api_list and parsed_result: # If parsed_result was a non-empty list but no valid items were found
                print(f"[ERROR] No valid API endpoints parsed from LLM result (list not empty but no valid items found): {result}")
        else:
            print(f"[ERROR] Expected JSON list for API endpoints, but received type: {type(parsed_result).__name__}. Raw: {result}")
    except json.JSONDecodeError:
        print(f"[ERROR] Invalid JSON from LLM for API endpoints: '{result}'. Falling back to empty list.")
    except Exception as e:
        print(f"[ERROR] An unexpected error occurred during API endpoint parsing: {e}. Falling back to empty list.")

    return {
        "api_endpoints": api_list,
        "tdd_text": [f"API endpoints extracted: {json.dumps(api_list)}"]
    }

def generate_backend_code(state: CodeGenState) -> dict:
    print(f"🚀 Generating {state.language} {state.backend} Backend API Code...")
    if not state.language or not state.backend or not state.api_endpoints:
        print("[WARNING] Skipping backend code generation: Missing language, backend framework, or API endpoints.")
        return {"backend_code": None}
    # Filter for all API endpoints relevant for backend generation, including inferred ones
    backend_api_endpoints = state.api_endpoints[:]
    # Manually add inferred login/register endpoints for backend generation if not already present
    inferred_backend_endpoints = [
        {"method": "POST", "path": "/api/customer/register", "description": "Customer Registration"},
        {"method": "POST", "path": "/api/customer/login", "description": "Customer Login"},
        {"method": "GET", "path": "/api/loan/application/status", "description": "Fetch Application Status"},
        {"method": "GET", "path": "/api/status/tracking", "description": "Fetch All Application Statuses"} # For the dashboard
    ]
    for inferred_ep in inferred_backend_endpoints:
        if not any(ep['path'] == inferred_ep['path'] for ep in backend_api_endpoints):
            backend_api_endpoints.append(inferred_ep)

    endpoints_str = json.dumps(backend_api_endpoints, indent=2)

    form_schemas_backend_str = ""
    if state.form_input_schemas:
        form_schemas_backend_str = "\n\nConsider the following form input schemas for request body definitions:\n"
        for form_name, schema in state.form_input_schemas.items():
            form_schemas_backend_str += f"- **{form_name} Data Model**: {json.dumps(schema, indent=2)}\n"
            
    table_schemas_backend_str = ""
    if state.table_schemas:
        table_schemas_backend_str = "\n\nConsider the following database table schemas for data persistence:\n"
        for table_name, columns in state.table_schemas.items():
            table_schemas_backend_str += f"- **Table {table_name}**: Columns: {', '.join(columns)}\n"


    prompt = f"""
You are a highly skilled {state.language} developer, specializing in the {state.backend} framework, connecting to a {state.database} database.
Generate the necessary boilerplate code for the following API endpoints, focusing on robust data handling and persistence.

General Instructions:

Data Models/Schemas:

Create data models/schemas for your chosen backend framework ({state.backend}) that correspond directly to the provided table_schemas.
Pay close attention to appropriate field types and primary/foreign key definitions, leveraging the {state.database} database capabilities.
For the Users table, consider an auto-incrementing integer primary key for customer_id and a JSON-compatible field for profile_details.
For Applications, ensure loan_amount uses a precise numeric type suitable for currency.
Define relationships between models (e.g., Application to User).

Request Body Validation/Serialization:
Create request body validation or serialization classes/structures (e.g., Pydantic models for FastAPI, REST Framework Serializers for Django, Joi schemas for Express.js) for each form schema provided in form_input_schemas.
Map these validation fields to the input fields of the forms.

API Endpoints Implementation:
For each API endpoint listed, create a corresponding endpoint handler (e.g., controller function, view class, route handler).

POST Endpoints (Data Creation/Submission):
Implement logic to validate incoming request data using the appropriate validation/serialization class.
If valid, save the data to the respective data model(s) in the {state.database} database.
Handle relationships (e.g., link Application to User).
Return appropriate HTTP responses (e.g., 201 Created, 400 Bad Request, 404 Not Found, 500 Internal Server Error).
For /api/customer/register, ensure a new user record is created.

GET Endpoints (Data Retrieval):
Implement logic to fetch data from the database.
For /api/loan/application/status, fetch a specific application's status.
For /api/status/tracking, implement logic to fetch all relevant application statuses (or a representative example) for the dashboard.

Routing/URL Configuration:
Define URL patterns or routes to map each API endpoint to its respective handler.
API Endpoints to Implement:
{endpoints_str}

Form Input Schemas for Request Bodies:
{form_schemas_backend_str}

Database Table Schemas for ORM/Data Models:
{table_schemas_backend_str}

Output all code in separate markdown blocks with explicit filenames appropriate for a {state.backend} project structure (e.g., models.py, serializers.py, views.py, urls.py for Django; main.py with Pydantic models for FastAPI; routes.js, models.js for Express.js).
"""
    result = ask_llm(prompt)
    return {"backend_code": result, "tdd_text": [f"Backend code generated for {state.language} {state.backend} (POST focus, SQL saving)"]}

def generate_sql_code(state: CodeGenState) -> dict:
    print(f"📂 Generating {state.database} SQL Schema Code...")
    if not state.database or not state.table_schemas:
        print("[WARNING] Skipping SQL code generation: Missing database type or table schemas.")
        return {"sql_code": None}

    schemas_str = json.dumps(state.table_schemas, indent=2)
    prompt = f"""
You are a SQL expert. Create DDL for the following schemas:
Database: {state.database}
Schemas:
{schemas_str}

Include CREATE TABLE statements with appropriate column types (e.g., SERIAL PRIMARY KEY, NUMERIC(15, 2), TEXT, TIMESTAMP WITH TIME ZONE, JSONB) and primary/foreign keys.
Output valid SQL in a markdown block.
"""
    result = ask_llm(prompt)
    return {"sql_code": result, "tdd_text": [f"SQL schema code generated for {state.database}"]}



def verify_combination(state: CodeGenState) -> dict:
    print("--- ENTERING verify_combination ---")
    current_tdd_text_combined = "\n".join(state.tdd_text if state.tdd_text else [])

    frontend = state.frontend_framework
    language = state.language
    backend = state.backend
    database = state.database

    print(f"Verifying combination: Frontend={frontend}, Language={language}, Backend={backend}, Database={database}")

    prompt = f"""
    You are an expert software architect.
    Given the following detected technologies, determine if they form a generally supported and compatible combination for building a modern web application.

    Frontend: {frontend}
    Language: {language}
    Backend: {backend}
    Database: {database}

    Consider common industry practices and established ecosystems.

    Respond with "True" if the combination is generally compatible and supported, otherwise respond with "False".
    Provide ONLY "True" or "False", no other text or explanation.
    """
    result = ask_llm(prompt).strip().lower()
    is_valid = (result == "true")
    print(f"Combination validation result: {is_valid}")

    new_tdd_entry = f"Technology combination validation: Frontend={frontend}, Language={language}, Backend={backend}, Database={database} -> Is Valid: {is_valid}."
    
    return {
        "is_valid_combination": is_valid,
        "tdd_text": [new_tdd_entry] # Return only new message
    }


workflow = StateGraph(CodeGenState)

# === Node Definitions ===
workflow.add_node("Start", start_node)
workflow.add_node("DetectFrontend", detect_frontend)
workflow.add_node("DetectLanguage", detect_language)
workflow.add_node("DetectBackend", detect_backend)
workflow.add_node("DetectDatabase", detect_database)
workflow.add_node("ExtractCustomerUI", extract_customer_ui_and_form_details) # Renamed from ExtractCustomerUIAndFormDetails
workflow.add_node("ExtractTableSchema", extract_table_schema)
workflow.add_node("ExtractApiEndpoints", extract_api_endpoints)
workflow.add_node("GenerateFrontendCode", generate_frontend_code)
workflow.add_node("GenerateBackendCode", generate_backend_code)
workflow.add_node("GenerateSQLCode", generate_sql_code)
workflow.add_node("VerifyCombo", verify_combination)
workflow.add_node("TriggerAllGenerators", trigger_all_generators)
workflow.add_node("CheckAllGenerated", check_all_generated) # Use the named function
workflow.add_node("WriteCodeToFiles", write_code_to_files)
workflow.add_node("ZipGeneratedCode", zip_generated_code)

# === Entry Point ===
# === Entry Point ===
workflow.set_entry_point("Start")

# === Phase 1: Detection and Extraction (Parallel) ===
workflow.add_edge("Start", "DetectFrontend")
workflow.add_edge("Start", "DetectLanguage")
workflow.add_edge("Start", "DetectBackend")
workflow.add_edge("Start", "DetectDatabase")

# Frontend detection leads directly to code generation via Extract UI
workflow.add_edge("DetectFrontend", "ExtractCustomerUI")
workflow.add_edge("ExtractCustomerUI", "GenerateFrontendCode")

# Backend and DB continue as usual
workflow.add_edge("DetectBackend", "ExtractApiEndpoints")
workflow.add_edge("DetectDatabase", "ExtractTableSchema")

workflow.add_edge("ExtractApiEndpoints", "GenerateBackendCode")
workflow.add_edge("ExtractTableSchema", "GenerateSQLCode")

# === Phase 2: Validation (Only for Backend & DB) ===
#workflow.add_edge("DetectLanguage", "VerifyCombo")
#workflow.add_edge("ExtractApiEndpoints", "VerifyCombo")
#workflow.add_edge("ExtractTableSchema", "VerifyCombo")
# ⛔ No edge from ExtractCustomerUI → VerifyCombo

# === Phase 3: Conditional Routing ===
#workflow.add_conditional_edges(
#    "VerifyCombo",
#    lambda state: "TRIGGER_GENERATORS" if state.is_valid_combination else "END_UNSUPPORTED_COMBO",
#    {
#        "TRIGGER_GENERATORS": "TriggerAllGenerators",
#        "END_UNSUPPORTED_COMBO": END
#    }
#)

# === Phase 4: Code Generation ===
# Frontend already triggered independently above
#workflow.add_edge("TriggerAllGenerators", "GenerateBackendCode")
#workflow.add_edge("TriggerAllGenerators", "GenerateSQLCode")

# === Phase 5: Synchronization before Writing Files ===
#workflow.add_edge("GenerateFrontendCode", "CheckAllGenerated")  # frontend joins here
#workflow.add_edge("GenerateBackendCode", "CheckAllGenerated")
#workflow.add_edge("GenerateSQLCode", "CheckAllGenerated")

# === Phase 6: Conditional Routing ===
#workflow.add_conditional_edges(
##    "CheckAllGenerated",
#    route_after_generation,
#    {
#        "WRITE_FILES": "WriteCodeToFiles",
#        "END": END
#    }
#)

workflow.add_edge("GenerateFrontendCode", "WriteCodeToFiles")  # frontend joins here
workflow.add_edge("GenerateBackendCode", "WriteCodeToFiles")
workflow.add_edge("GenerateSQLCode", "WriteCodeToFiles")

# === Phase 7: Finalization ===
workflow.add_edge("WriteCodeToFiles", "ZipGeneratedCode")
workflow.add_edge("ZipGeneratedCode", END)

# === Compile ===
app = workflow.compile()

# --- Workflow Definition ---
def create_workflow():
    # ... (rest of create_workflow function content) ...
    return workflow.compile()

# This is the compiled app instance, ready to be used by FastAPI
langgraph_app = create_workflow()



#print("\n LangGraph Flow (ASCII)")
print(app.get_graph().draw_ascii())
#print(app.get_graph().draw_mermaid_png())
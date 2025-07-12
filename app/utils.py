import re
import os
from typing import List, Dict, Optional

def parse_code_blocks(text: str, component_names: Optional[List[str]] = None, frontend_framework: Optional[str] = None) -> List[Dict[str, str]]:
    """
    Parses code blocks from a given text, attempting to infer language and filename.

    Args:
        text (str): The input text, typically an LLM response, containing code blocks.
        component_names (Optional[List[str]]): A list of expected component names (e.g., ["LoginComponent"]).
                                                 Used for smarter filename inference.
        frontend_framework (Optional[str]): The detected frontend framework (e.g., "Angular", "React").
                                            Used to guide language and filename inference.

    Returns:
        List[Dict[str, str]]: A list of dictionaries, each containing 'filename' and 'code'.
    """
    files = []
    # Regex Explanation:
    # ```(?P<lang>\w+)?      -> Matches ``` followed by an optional language (e.g., python, js, ts, html)
    # (?:filename: (?P<filename>[^\n]+?))? -> Non-capturing group for optional "filename: " and captures the filename
    # \n(?P<code>.*?)       -> Matches newline, then captures the code (non-greedy)
    # \n```                  -> Matches newline, then closing ```
    # re.DOTALL              -> Allows '.' to match newlines, essential for multi-line code blocks
    matches = re.finditer(r"```(?P<lang>\w+)?(?:filename: (?P<filename>[^\n]+?))?\n(?P<code>.*?)\n```", text, re.DOTALL)

    # Convert component names to kebab-case for easier matching in filenames/paths
    # Example: "MyComponent" -> "my-component"
    lowercased_component_kebab = [re.sub(r'(?<!^)(?=[A-Z])', '-', comp).lower() for comp in component_names] if component_names else []

    for match in matches:
        # Extract matched groups, default to 'txt' if no language specified
        lang = (match.group('lang') or 'txt').lower() # Ensure language is lowercase for consistent comparison
        llm_provided_filename = (match.group('filename') or "").strip() # Handle None and strip whitespace
        code = match.group('code').strip()

        inferred_filename = None

        # --- Enhanced Language Detection based on framework context ---
        # This is a very smart approach to refine the LLM's sometimes ambiguous 'js' tag.
        if lang in ['javascript', 'js']:
            if frontend_framework == "Angular":
                if ("import { Component } from '@angular/core';" in code or
                    "@Component({" in code or
                    "templateUrl:" in code or
                    "styleUrls:" in code):
                    lang = "typescript" # Angular components are typically TypeScript
                elif ("<div" in code or "<span" in code or "<p>" in code or
                      "<form" in code or "<button" in code or "<app-" in code):
                    lang = "html" # Detects HTML content
                elif ("{" in code and "}" in code and ":" in code and ";" in code and
                      ("px" in code or "em" in code or "rem" in code or "#" in code or "." in code)):
                    lang = "css" # Detects CSS content
            elif frontend_framework == "React":
                if ("import React from 'react';" in code or
                    "React.createElement(" in code or
                    ("function " in code and "return (" in code) or # Common React functional component patterns
                    ("const " in code and "return (" in code) or
                    (".jsx" in llm_provided_filename or ".js" in llm_provided_filename)): # Check original filename hint
                    lang = "jsx" # React components are typically JSX
                elif ("{" in code and "}" in code and ":" in code and ";" in code and
                      ("px" in code or "em" in code or "rem" in code or "#" in code or "." in code)):
                    lang = "css" # Detects CSS content

        # --- Smarter Filename Inference ---
        # Prioritize LLM-provided filename if it looks legitimate.
        # Fallback to inference if filename is missing or generic.
        if not llm_provided_filename or \
           re.search(r'^(unnamed|script|output|file|example)(\s|$)', llm_provided_filename, re.IGNORECASE):
            # Try to match a component name within the code content
            matched_component_kebab = None
            for comp_kebab in lowercased_component_kebab:
                # Compare component name (cleaned) against code content (cleaned)
                if comp_kebab.replace('-', '').lower() in code.lower().replace('-', ''):
                    matched_component_kebab = comp_kebab
                    break

            if matched_component_kebab:
                if frontend_framework == "Angular":
                    if lang in ["typescript", "ts"]:
                        inferred_filename = f"src/app/{matched_component_kebab}/{matched_component_kebab}.component.ts"
                    elif lang == "html":
                        inferred_filename = f"src/app/{matched_component_kebab}/{matched_component_kebab}.component.html"
                    elif lang == "css":
                        inferred_filename = f"src/app/{matched_component_kebab}/{matched_component_kebab}.component.css"
                    else:
                        inferred_filename = f"src/app/{matched_component_kebab}/{matched_component_kebab}_angular_code.{lang}"
                elif frontend_framework == "React":
                    # Convert kebab-case to PascalCase for React component filenames
                    comp_pascal = "".join([s.capitalize() for s in matched_component_kebab.split('-')])
                    if lang in ["javascript", "js", "jsx"]:
                        inferred_filename = f"src/components/{comp_pascal}.jsx"
                    elif lang == "css":
                        inferred_filename = f"src/components/{matched_component_kebab}.module.css" # Often .module.css in React
                        # Consider if you want to differentiate between global and module CSS
                    else:
                        inferred_filename = f"src/components/{matched_component_kebab}_react_code.{lang}"
            
            # If no component match, try framework-specific common files
            if not inferred_filename:
                if frontend_framework == "Angular":
                    if "platformBrowserDynamic().bootstrapModule(AppModule)" in code: inferred_filename = "src/main.ts"
                    elif "NgModule" in code and "declarations" in code: inferred_filename = "src/app/app.module.ts"
                    elif "selector: 'app-root'" in code and "templateUrl" in code: inferred_filename = "src/app/app.component.ts"
                    elif "<router-outlet>" in code or "app-root" in code: inferred_filename = "src/app/app.component.html"
                    elif "body {" in code or "html {" in code: inferred_filename = "src/styles.css"
                    # General fallbacks if no specific pattern matched
                    elif lang in ["typescript", "ts"]: inferred_filename = "src/app/app.component.ts"
                    elif lang == "html": inferred_filename = "src/app/app.component.html"
                    elif lang == "css": inferred_filename = "src/styles.css"
                    else: inferred_filename = f"angular_default.{lang}"
                elif frontend_framework == "React":
                    if "ReactDOM.createRoot" in code: inferred_filename = "src/main.jsx" # Or index.js/jsx
                    elif "function App()" in code or "const App =" in code: inferred_filename = "src/App.jsx"
                    elif "body {" in code or "html {" in code: inferred_filename = "src/index.css" # Global CSS
                    # General fallbacks
                    elif lang in ["javascript", "js", "jsx"]: inferred_filename = "src/App.jsx"
                    elif lang == "css": inferred_filename = "src/App.css" # Component-specific or general
                    else: inferred_filename = f"react_default.{lang}"
                # Add logic for backend parsing if no frontend framework or no frontend match
                elif lang == "python":
                    if re.search(r"class\s+\w*Model\(", code, re.IGNORECASE) or "models.Model" in code: inferred_filename = "backend/models.py"
                    elif re.search(r"class\s+\w*ViewSet\(", code) or "APIView" in code or "router = APIRouter()" in code: inferred_filename = "backend/views.py"
                    elif re.search(r"class\s+\w*Serializer\(", code): inferred_filename = "backend/serializers.py"
                    elif "urlpatterns" in code or "path(" in code or "re_path(" in code: inferred_filename = "backend/urls.py"
                    elif ("app = FastAPI(" in code or "from flask import Flask" in code) and ("main.py" in llm_provided_filename or "app.py" in llm_provided_filename): inferred_filename = "backend/main.py"
                    elif "__name__ == \"__main__\"" in code and ("import fastapi" in code or "import flask" in code): inferred_filename = "backend/main.py"
                    else: inferred_filename = "backend/app_script.py"
                elif lang in ["javascript", "js", "jsx"]: # For Node.js backend
                    if re.search(r"app\.use\(.*\)\s*;\s*router", code) or "express.Router()" in code: inferred_filename = "backend/routes.js"
                    elif re.search(r"mongoose\.Schema|new\s+\w+Schema\(", code) or "module.exports = mongoose.model" in code: inferred_filename = "backend/models.js"
                    elif "app.listen(" in code or "http.createServer" in code or "const app = express()" in code: inferred_filename = "backend/server.js"
                    else: inferred_filename = "backend/app_script.js"
                elif lang == "java": inferred_filename = "backend/Controller.java" # Generic Java backend default
                elif lang == "sql": inferred_filename = "backend/schema.sql" # Generic SQL default
                else: inferred_filename = f"unnamed_file.{lang}" # Final fallback

        # If after all inference, no filename, use a generic fallback based on original LLM hint or lang
        if not inferred_filename:
            inferred_filename = llm_provided_filename if llm_provided_filename else f"unnamed_code_block.{lang}"

        filename_to_use = inferred_filename.strip().replace(" ", "_").replace("/", os.sep)
        
        # --- Ensure Correct File Extensions ---
        # This section is critical for ensuring files are correctly typed by the OS/IDE.
        # Use re.search for more robust extension checking, including .component.ts etc.
        # Make sure to handle cases where LLM might provide `MyComponent.ts` when it should be `.component.ts`
        
        # Map common language names to their primary extensions
        extension_map = {
            "typescript": ".ts", "ts": ".ts",
            "javascript": ".js", "js": ".js", "jsx": ".jsx",
            "html": ".html",
            "css": ".css",
            "python": ".py",
            "java": ".java",
            "sql": ".sql",
            # Add more as needed
        }

        # Check if the filename already has a suitable extension for the detected language
        current_ext = os.path.splitext(filename_to_use)[1].lower()
        required_ext = extension_map.get(lang)

        if required_ext and current_ext != required_ext:
            # If the current extension is not the preferred one, or if it's generic like .txt
            # and there's a more specific one for the inferred language.
            # Avoid double extensions (e.g., file.js.ts)
            if current_ext and current_ext in [".txt", ".code"] and required_ext: # More specific check
                 filename_to_use = filename_to_use.rsplit('.', 1)[0] + required_ext if '.' in filename_to_use else filename_to_use + required_ext
            elif not current_ext and required_ext: # No extension, just add it
                filename_to_use += required_ext
            # Special handling for Angular components if relevant
            if frontend_framework == "Angular" and lang == "typescript" and "component" in filename_to_use.lower() and not re.search(r'\.component\.ts$', filename_to_use, re.IGNORECASE):
                filename_to_use = filename_to_use.rsplit('.', 1)[0] + ".component.ts" if '.' in filename_to_use else filename_to_use + ".component.ts"
            elif frontend_framework == "Angular" and lang == "html" and "component" in filename_to_use.lower() and not re.search(r'\.component\.html$', filename_to_use, re.IGNORECASE):
                filename_to_use = filename_to_use.rsplit('.', 1)[0] + ".component.html" if '.' in filename_to_use else filename_to_use + ".component.html"
            elif frontend_framework == "Angular" and lang == "css" and "component" in filename_to_use.lower() and not re.search(r'\.component\.css$', filename_to_use, re.IGNORECASE):
                filename_to_use = filename_to_use.rsplit('.', 1)[0] + ".component.css" if '.' in filename_to_use else filename_to_use + ".component.css"
            elif frontend_framework == "React" and lang == "jsx" and not filename_to_use.lower().endswith(".jsx"):
                filename_to_use = filename_to_use.rsplit('.', 1)[0] + ".jsx" if '.' in filename_to_use else filename_to_use + ".jsx"
            elif frontend_framework == "React" and lang == "css" and "module" in filename_to_use.lower() and not filename_to_use.lower().endswith(".module.css"):
                filename_to_use = filename_to_use.rsplit('.', 1)[0] + ".module.css" if '.' in filename_to_use else filename_to_use + ".module.css"
            elif not current_ext and required_ext: # If no extension was there, just add the required one
                 filename_to_use += required_ext
            elif current_ext not in extension_map.values() and required_ext: # If an unrecognized extension, replace it
                 filename_to_use = os.path.splitext(filename_to_use)[0] + required_ext


        # Normalize path separators (already done by .replace("/", os.sep))
        # Ensure that the filename doesn't start with a path separator if it's already an absolute path or relative from root.
        # This function is meant to produce relative paths (e.g., src/app/...).
        filename_to_use = os.path.normpath(filename_to_use)
        if filename_to_use.startswith(os.sep) and len(filename_to_use) > 1:
            filename_to_use = filename_to_use[1:] # Remove leading separator if it results in an absolute path

        files.append({"filename": filename_to_use, "code": code})
    return files
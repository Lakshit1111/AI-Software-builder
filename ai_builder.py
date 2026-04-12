import sys
import os
import subprocess
import json
import time
import tempfile
import shutil
import ast
import re
import signal
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QHBoxLayout, QTextEdit, QLabel, QPushButton,
                               QLineEdit, QComboBox, QGroupBox, QProgressBar, QMessageBox,
                               QSplitter, QTabWidget, QFileDialog, QDialog, QCheckBox)
from PySide6.QtCore import QThread, Signal, Slot
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# 1. DATA STRUCTURES (The "Blackboard")
# ==========================================

class State(Enum):
    INIT = auto()
    ENHANCING = auto()
    PLANNING = auto()
    CODING = auto()
    TESTING = auto()
    FIXING = auto()
    TERMINAL_APPROVAL = auto()
    FINISHED = auto()
    FAILED = auto()


def load_skills():
    try:
        with open("skills.md", "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""

SKILLS = load_skills()


@dataclass
class FileOperation:
    operation: str  # "create", "update", "delete"
    path: str
    content: str = ""


@dataclass
class TerminalCommand:
    command: str
    description: str
    approved: bool = False


@dataclass
class ProjectContext:
    original_prompt: str = ""
    enhanced_prompt: str = ""
    plan: List[str] = field(default_factory=list)
    current_step_index: int = 0

    files: Dict[str, str] = field(default_factory=dict)
    file_operations: List[FileOperation] = field(default_factory=list)

    last_error: str = ""
    error_traceback: str = ""
    syntax_errors: str = ""
    attempt_count: int = 0
    max_retries: int = 5

    pending_commands: List[TerminalCommand] = field(default_factory=list)
    approved_commands: List[str] = field(default_factory=list)

    project_type: str = "unknown"

    def get_file(self, path: str) -> str:
        return self.files.get(path, "")

    def set_file(self, path: str, content: str):
        self.files[path] = content
        self.file_operations.append(FileOperation("create" if path not in self.files else "update", path, content))

    def delete_file(self, path: str):
        if path in self.files:
            del self.files[path]
            self.file_operations.append(FileOperation("delete", path))

    def get_all_files_summary(self) -> str:
        if not self.files:
            return "(No files yet)"
        lines = []
        for path, content in self.files.items():
            line_count = len(content.splitlines())
            lines.append(f"  {path} ({line_count} lines)")
        return "\n".join(lines)

    def detect_project_type(self):
        all_code = "\n".join(self.files.values())
        if "PySide6" in all_code or "PyQt" in all_code:
            self.project_type = "pyside_gui"
        elif "tkinter" in all_code:
            self.project_type = "tkinter_gui"
        elif "import sys" in all_code and ("input(" in all_code or "print(" in all_code):
            self.project_type = "cli"
        else:
            self.project_type = "script"


class Sandbox:
    def __init__(self):
        self.work_dir: str = ""
        self._create_sandbox()

    def _create_sandbox(self):
        self.work_dir = tempfile.mkdtemp(prefix="ai_builder_sandbox_")

    def write_files(self, files: Dict[str, str]):
        for path, content in files.items():
            full_path = os.path.join(self.work_dir, path)
            dir_name = os.path.dirname(full_path)
            os.makedirs(dir_name if dir_name else self.work_dir, exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)

    def run_code(self, main_file: str = "main.py", timeout: int = 10) -> Tuple[str, str, int]:
        full_path = os.path.join(self.work_dir, main_file)
        if not os.path.exists(full_path):
            return "", f"File not found: {main_file}", 1

        all_code = ""
        for root, dirs, files in os.walk(self.work_dir):
            for f in files:
                if f.endswith(".py"):
                    try:
                        with open(os.path.join(root, f), "r", encoding="utf-8") as fh:
                            all_code += fh.read() + "\n"
                    except Exception:
                        pass

        is_gui = any(x in all_code for x in ["tkinter", "PySide6", "PyQt", "customtkinter", "wx", "PySimpleGUI"])

        env = os.environ.copy()
        env["PYTHONPATH"] = self.work_dir
        env["PYTHONDONTWRITEBYTECODE"] = "1"

        try:
            result = subprocess.run(
                [sys.executable, "-u", full_path],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.work_dir,
                env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
            return result.stdout.strip(), result.stderr.strip(), result.returncode
        except subprocess.TimeoutExpired:
            if is_gui:
                return "", "", 0
            return "", "Execution timed out", -1
        except Exception as e:
            return "", str(e), 1

    def cleanup(self):
        if self.work_dir and os.path.exists(self.work_dir):
            try:
                shutil.rmtree(self.work_dir)
            except Exception:
                pass


def check_syntax(code: str) -> str:
    try:
        ast.parse(code)
        return ""
    except SyntaxError as e:
        return f"SyntaxError line {e.lineno}: {e.msg}"


def parse_multi_file_response(text: str) -> Dict[str, str]:
    files = {}
    pattern = r'```(?:python)?\s*(?:\[([^\]]+)\])?\s*\n(.*?)```'
    matches = re.findall(pattern, text, re.DOTALL)

    if matches:
        for filename, code in matches:
            if filename:
                filename = filename.strip()
            else:
                filename = "main.py"
            files[filename] = code.strip()
    else:
        lines = text.split('\n')
        code_lines = []
        code_started = False
        for line in lines:
            if line.strip().startswith(("import ", "from ", "def ", "class ", "#", "if __name__")):
                code_started = True
            if code_started:
                code_lines.append(line)
        if code_lines:
            files["main.py"] = "\n".join(code_lines).strip()

    return files


def extract_commands(text: str) -> List[TerminalCommand]:
    commands = []
    pattern = r'```(?:bash|sh|shell|cmd|powershell)?\s*\n(.*?)```'
    matches = re.findall(pattern, text, re.DOTALL)
    for match in matches:
        cmd = match.strip()
        if cmd and not cmd.startswith("#"):
            desc = cmd.split('\n')[0]
            commands.append(TerminalCommand(command=cmd, description=desc))
    return commands


# ==========================================
# 2. BACKEND ABSTRACTION
# ==========================================

import requests
import ollama


class LLMProvider:
    def __init__(
        self,
        provider_type: str,
        model_name: str,
        api_url: str = "https://sia.sansol.in:9000/v1",
        api_key: str = "",
        verify_ssl: bool = False,
        timeout: int = 120
    ):
        self.provider_type = provider_type
        self.model_name = model_name
        self.api_url = api_url or "https://sia.sansol.in:9000/v1"
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.verify_ssl = verify_ssl
        self.timeout = timeout

        if self.provider_type == "Ollama":
            self.client = ollama.Client(host="http://localhost:11434")

    def chat(self, messages, temperature=0.7, system_prompt=None):
        try:
            if self.provider_type == "vLLM / OpenAI":
                return self._chat_vllm(messages, temperature, system_prompt)
            elif self.provider_type == "Ollama":
                return self._chat_ollama(messages, temperature)
            else:
                raise ValueError("Unsupported provider type")
        except Exception as e:
            return f"API_ERROR: {str(e)}"

    def _chat_vllm(self, messages, temperature, system_prompt):
        url = f"{self.api_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        final_messages = []
        if system_prompt:
            final_messages.append({"role": "system", "content": system_prompt})
        final_messages.extend(messages)
        payload = {
            "model": self.model_name,
            "messages": final_messages,
            "temperature": temperature
        }
        r = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=self.timeout,
            verify=self.verify_ssl
        )
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text}")
        return r.json()["choices"][0]["message"]["content"]

    def _chat_ollama(self, messages, temperature):
        response = self.client.chat(
            model=self.model_name,
            messages=messages,
            options={"temperature": temperature}
        )
        return response["message"]["content"]


# ==========================================
# 3. AGENT DEFINITIONS
# ==========================================

class BaseAgent:
    def __init__(self, llm: LLMProvider):
        self.llm = llm


class PromptEnhancer(BaseAgent):
    def enhance(self, user_prompt):
        system_prompt = f"""
{SKILLS}

[ROLE: ENHANCER]
You are an Expert Product Manager and Requirements Engineer.
Your job is to take a brief user request for a software application and expand it into a comprehensive, unambiguous technical prompt.

Strict Rules:
1. Identify the core functionality, necessary UI/CLI components, and edge cases.
2. If it is a GUI application, explicitly specify its structure in detail (windows, buttons, layouts).
3. Detail the expected behavior (e.g., 'Input fields must clear after submission', 'Errors must be caught and displayed safely').
4. Do not write code. Do not write the implementation steps.
5. Output ONLY the enhanced, detailed project description. No conversational intro.
"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Brief Request: {user_prompt}\n\nPlease provide the enhanced technical description."}
        ]
        return self.llm.chat(messages, temperature=0.2)


class Planner(BaseAgent):
    def create_plan(self, user_prompt):
        system_prompt = f"""
{SKILLS}

[ROLE: Planner]
You are responsible for breaking down a project into clear, executable steps.

Focus:
- Convert the project into 4-8 concrete implementation steps
- Each step must produce a meaningful code change
- Steps must be ordered logically and build on each other
- Include file creation/modification details in each step

Output Rules:
- Return ONLY a numbered list
- No explanations
- No markdown
"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Project: {user_prompt}"}
        ]
        return self.llm.chat(messages, temperature=0.1)


class Developer(BaseAgent):
    def write_code(self, task, context: ProjectContext):
        system_prompt = f"""
{SKILLS}

[ROLE: Developer]
You are an expert Python developer. You write clean, well-structured code.

Focus:
- Implement the given task into the existing codebase
- Maintain compatibility with existing functionality
- Use proper error handling (try/except) for all operations
- For GUI apps (tkinter/PySide6), ensure the mainloop runs correctly
- For CLI apps, handle user input gracefully

Multi-File Rules:
- If the task requires multiple files, output ALL files in a single response
- Use the format: ```[filename.py]\ncode here\n```
- Always include main.py
- Import local modules relative to the project directory

Output Rules:
- Return ONLY the code, no explanations
- Use markdown code blocks with filenames: ```[filename.py]
"""
        file_context = ""
        for path, content in context.files.items():
            file_context += f"\n--- {path} ---\n{content}\n"

        if not file_context:
            file_context = "(No existing files)"

        user_msg = f"""
Project Goal: {context.original_prompt}

Current Task: {task}

Existing Files:
{file_context}

Project Type: {context.project_type}

Return all files needed to complete this task.
"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg}
        ]
        response = self.llm.chat(messages, temperature=0.1)
        return parse_multi_file_response(response)

    def fix_code(self, context: ProjectContext):
        system_prompt = f"""
{SKILLS}

[ROLE: Expert Debugger]
You are responsible for fixing errors in an existing Python codebase.

CRITICAL: Analyze the error carefully before making changes.
- Read the full error message and traceback
- Identify the EXACT line causing the issue
- Make the minimal fix needed, do not rewrite working code
- If the error is a missing import, add it
- If the error is a typo, fix the typo
- If the error is logical, correct the logic

Focus:
- Identify the root cause of the error
- Modify the code to resolve the issue
- Preserve all working functionality

Multi-File Rules:
- If the fix requires changes in multiple files, output ALL of them
- Use the format: ```[filename.py]\ncode here\n```

Output Rules:
- Return ONLY the corrected code, no explanations
- Use markdown code blocks with filenames: ```[filename.py]
"""
        error_context = f"""
ERROR TYPE: {self._classify_error(context.last_error)}

ERROR MESSAGE:
{context.last_error}

SYNTAX ERRORS:
{context.syntax_errors if context.syntax_errors else "None"}

TRACEBACK:
{context.error_traceback if context.error_traceback else "N/A"}
"""
        file_context = ""
        for path, content in context.files.items():
            file_context += f"\n--- {path} ---\n{content}\n"

        user_msg = f"""
{error_context}

Current Files:
{file_context}

Task: Fix the error and return ALL corrected files.
"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg}
        ]
        response = self.llm.chat(messages, temperature=0.1)
        return parse_multi_file_response(response)

    def _classify_error(self, error: str) -> str:
        error_lower = error.lower()
        if "syntaxerror" in error_lower or "invalid syntax" in error_lower:
            return "Syntax Error"
        elif "nameerror" in error_lower:
            return "NameError - Undefined variable or missing import"
        elif "typeerror" in error_lower:
            return "TypeError - Wrong data type used"
        elif "attributeerror" in error_lower:
            return "AttributeError - Object has no such method/attribute"
        elif "importerror" in error_lower or "modulenotfounderror" in error_lower:
            return "ImportError - Missing module or package"
        elif "indexerror" in error_lower:
            return "IndexError - List/tuple index out of range"
        elif "keyerror" in error_lower:
            return "KeyError - Dictionary key not found"
        elif "traceback" in error_lower:
            return "Runtime Error"
        elif "timed out" in error_lower:
            return "Timeout - Execution took too long"
        else:
            return "Unknown Error"


# ==========================================
# 4. STATE MACHINE WORKER (The "Brain")
# ==========================================

class StateMachineWorker(QThread):
    log_signal = Signal(str)
    finished_signal = Signal(bool, str)
    command_signal = Signal(str)
    command_response_signal = Signal(bool)

    def __init__(self, user_prompt, config):
        super().__init__()
        self.user_prompt = user_prompt
        self.config = config
        self.is_running = True
        self._pending_command = False
        self._command_approved = False
        self._context: Optional[ProjectContext] = None

    def run(self):
        self.log("Initializing AI State Machine...")

        try:
            llm = LLMProvider(
                provider_type=self.config['provider_type'],
                model_name=self.config['model_name'],
                api_url=self.config.get('api_url'),
                api_key=self.config.get('api_key', ''),
                timeout=120
            )
            enhancer = PromptEnhancer(llm)
            planner = Planner(llm)
            developer = Developer(llm)
        except Exception as e:
            self.finished_signal.emit(False, f"Setup Error: {e}")
            return

        context = ProjectContext(original_prompt=self.user_prompt)
        self._context = context
        current_state = State.INIT
        sandbox = Sandbox()

        while self.is_running and current_state not in [State.FINISHED, State.FAILED]:

            if current_state == State.INIT:
                self.log(f"State: {current_state.name}")
                current_state = State.ENHANCING

            elif current_state == State.ENHANCING:
                self.log(f"State: {current_state.name} - Enhancing prompt...")
                result = enhancer.enhance(context.original_prompt)
                if result.startswith("API_ERROR"):
                    self.finished_signal.emit(False, f"Enhancer failed: {result}")
                    return
                context.enhanced_prompt = result
                self.log(f"Enhanced prompt generated ({len(result)} chars)")
                current_state = State.PLANNING

            elif current_state == State.PLANNING:
                self.log(f"State: {current_state.name} - Architecting solution...")
                raw_plan = planner.create_plan(context.enhanced_prompt or context.original_prompt)
                if raw_plan.startswith("API_ERROR"):
                    self.finished_signal.emit(False, f"Planner failed: {raw_plan}")
                    return

                context.plan = []
                for line in raw_plan.split('\n'):
                    line = line.strip()
                    if not line:
                        continue
                    cleaned = re.sub(r'^[\d\-\*\.\s]+', '', line).strip()
                    if cleaned:
                        context.plan.append(cleaned)

                if not context.plan:
                    context.plan = [context.enhanced_prompt or context.original_prompt]

                self.log(f"Plan generated with {len(context.plan)} steps:")
                for i, step in enumerate(context.plan, 1):
                    self.log(f"  {i}. {step}")

                current_state = State.CODING

            elif current_state == State.CODING:
                if context.current_step_index >= len(context.plan):
                    current_state = State.FINISHED
                    continue

                step_desc = context.plan[context.current_step_index]
                self.log(f"\nState: {current_state.name} - Step {context.current_step_index + 1}/{len(context.plan)}")
                self.log(f"  Task: {step_desc}")

                context.detect_project_type()
                new_files = developer.write_code(step_desc, context)

                if not new_files:
                    self.log("WARNING: Developer returned no files. Retrying...")
                    context.attempt_count += 1
                    if context.attempt_count >= context.max_retries:
                        self.log("Max retries on coding. Moving on.")
                        context.attempt_count = 0
                        context.current_step_index += 1
                        current_state = State.CODING
                    continue

                context.attempt_count = 0
                for path, content in new_files.items():
                    context.set_file(path, content)
                    self.log(f"  Created/Updated: {path}")

                current_state = State.TESTING

            elif current_state == State.TESTING:
                self.log(f"State: {current_state.name} - Verifying code...")

                syntax_ok = True
                for path, code in context.files.items():
                    syn_err = check_syntax(code)
                    if syn_err:
                        self.log(f"  Syntax error in {path}: {syn_err}")
                        context.syntax_errors += f"{path}: {syn_err}\n"
                        syntax_ok = False

                if not syntax_ok:
                    context.last_error = "Syntax errors detected:\n" + context.syntax_errors
                    context.error_traceback = ""
                    current_state = State.FIXING
                    continue

                sandbox.cleanup()
                sandbox = Sandbox()
                sandbox.write_files(context.files)

                main_file = self._resolve_main_file(context.files)
                stdout, stderr, returncode = sandbox.run_code(main_file, timeout=8)

                if returncode != 0:
                    error_msg = stderr if stderr else f"Process exited with code {returncode}"
                    self.log(f"  Test Failed: {error_msg[:200]}")
                    context.last_error = error_msg
                    context.error_traceback = stderr
                    current_state = State.FIXING
                else:
                    self.log("  Test Passed.")
                    context.attempt_count = 0
                    context.current_step_index += 1

                    if context.pending_commands:
                        current_state = State.TERMINAL_APPROVAL
                    elif context.current_step_index >= len(context.plan):
                        current_state = State.FINISHED
                    else:
                        current_state = State.CODING

            elif current_state == State.FIXING:
                if context.attempt_count >= context.max_retries:
                    self.log(f"WARNING: Max fix retries ({context.max_retries}) reached.")
                    self.log("Moving to next step with current code.")
                    context.attempt_count = 0
                    context.current_step_index += 1
                    context.syntax_errors = ""
                    context.error_traceback = ""
                    if context.current_step_index >= len(context.plan):
                        current_state = State.FAILED
                    else:
                        current_state = State.CODING
                else:
                    context.attempt_count += 1
                    self.log(f"State: {current_state.name} - Attempt {context.attempt_count}/{context.max_retries}")
                    self.log(f"  Error: {context.last_error[:150]}")

                    fixed_files = developer.fix_code(context)

                    if not fixed_files:
                        self.log("WARNING: Fixer returned no files. Retrying...")
                        continue

                    context.syntax_errors = ""
                    context.error_traceback = ""

                    for path, content in fixed_files.items():
                        context.set_file(path, content)

                    current_state = State.TESTING

            elif current_state == State.TERMINAL_APPROVAL:
                if not context.pending_commands:
                    if context.current_step_index >= len(context.plan):
                        current_state = State.FINISHED
                    else:
                        current_state = State.CODING
                    continue

                cmd = context.pending_commands.pop(0)
                self.log(f"\nTerminal command requested: {cmd.command}")
                self.log(f"Description: {cmd.description}")

                self._pending_command = True
                self._command_approved = False
                self.command_signal.emit(json.dumps({
                    "command": cmd.command,
                    "description": cmd.description
                }))

                while self._pending_command and self.is_running:
                    time.sleep(0.1)

                if self._command_approved:
                    self.log(f"  Executing: {cmd.command}")
                    try:
                        result = subprocess.run(
                            cmd.command,
                            shell=True,
                            capture_output=True,
                            text=True,
                            timeout=30,
                            cwd=sandbox.work_dir,
                            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                        )
                        if result.stdout:
                            self.log(f"  Output: {result.stdout[:500]}")
                        if result.returncode != 0:
                            self.log(f"  Warning: Exit code {result.returncode}")
                            if result.stderr:
                                self.log(f"  Stderr: {result.stderr[:300]}")
                        context.approved_commands.append(cmd.command)
                    except Exception as e:
                        self.log(f"  Command failed: {e}")
                else:
                    self.log(f"  Command skipped by user.")

                self._pending_command = False

                if context.pending_commands:
                    current_state = State.TERMINAL_APPROVAL
                elif context.current_step_index >= len(context.plan):
                    current_state = State.FINISHED
                else:
                    current_state = State.CODING

        sandbox.cleanup()

        if current_state == State.FINISHED:
            self.save_project(context)
            self.log("\nProject Build Complete!")
            self.finished_signal.emit(True, f"Project saved. {len(context.files)} file(s) created.")
        elif not self.is_running:
            self.finished_signal.emit(False, "Process stopped by user.")
        else:
            self.finished_signal.emit(False, "Build Failed - max retries exceeded.")

    def approve_command(self, approved: bool):
        self._command_approved = approved
        self._pending_command = False

    def _resolve_main_file(self, files: Dict[str, str]) -> str:
        if "main.py" in files:
            return "main.py"
        for path in files:
            if path.endswith("/main.py") or path.endswith("\\main.py"):
                return path
        for path in files:
            if path.endswith(".py"):
                return path
        return list(files.keys())[0]

    def save_project(self, context):
        project_dir = "generated_app"
        os.makedirs(project_dir, exist_ok=True)
        for path, content in context.files.items():
            full_path = os.path.join(project_dir, path)
            os.makedirs(os.path.dirname(full_path) if os.path.dirname(full_path) else project_dir, exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)

        with open(os.path.join(project_dir, "build_log.json"), "w", encoding="utf-8") as f:
            json.dump({
                "plan": context.plan,
                "steps_completed": context.current_step_index,
                "files": list(context.files.keys()),
                "project_type": context.project_type,
                "approved_commands": context.approved_commands
            }, f, indent=2)

    def log(self, msg):
        self.log_signal.emit(msg)

    def stop(self):
        self.is_running = False
        self._pending_command = False


# ==========================================
# 5. UI IMPLEMENTATION
# ==========================================

class CommandApprovalDialog(QDialog):
    def __init__(self, command, description, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Terminal Command Approval")
        self.setMinimumWidth(500)
        self.approved = False

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("The AI wants to run this command:"))

        cmd_label = QLabel(command)
        cmd_label.setStyleSheet("background-color: #333; color: #0f0; font-family: Consolas; padding: 10px;")
        cmd_label.setWordWrap(True)
        layout.addWidget(cmd_label)

        layout.addWidget(QLabel(f"Description: {description}"))

        self.dont_ask = QCheckBox("Don't ask again for safe commands (pip install, mkdir, etc.)")
        layout.addWidget(self.dont_ask)

        btn_layout = QHBoxLayout()
        btn_deny = QPushButton("Deny")
        btn_deny.setStyleSheet("background-color: #D32F2F; color: white; padding: 8px;")
        btn_deny.clicked.connect(lambda: self._respond(False))

        btn_approve = QPushButton("Approve")
        btn_approve.setStyleSheet("background-color: #4CAF50; color: white; padding: 8px;")
        btn_approve.clicked.connect(lambda: self._respond(True))

        btn_layout.addWidget(btn_deny)
        btn_layout.addWidget(btn_approve)
        layout.addLayout(btn_layout)

    def _respond(self, approved):
        self.approved = approved
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Cognitive AI Builder - Multi-File")
        self.resize(1200, 900)
        self._safe_commands = {"pip", "pip3", "mkdir", "echo", "cd", "dir", "ls", "python -m pip"}
        self.setup_ui()

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        header = QLabel("Cognitive AI Builder - Multi-File, Sandbox, Terminal Approval")
        header.setStyleSheet("font-size: 18px; font-weight: bold; color: #4CAF50;")
        main_layout.addWidget(header)

        config_group = QGroupBox("LLM Configuration")
        config_layout = QHBoxLayout()

        self.combo_provider = QComboBox()
        self.combo_provider.addItems(["Ollama", "vLLM / OpenAI"])
        self.combo_provider.currentTextChanged.connect(self.toggle_inputs)

        self.input_model = QLineEdit("sia")
        self.input_url = QLineEdit()
        self.input_url.setPlaceholderText("https://sia.sansol.in:9000/v1")
        self.input_key = QLineEdit()
        self.input_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_key.setPlaceholderText("Bearer Token (INTERNAL-LLM-TOKEN)")

        config_layout.addWidget(QLabel("Provider:"))
        config_layout.addWidget(self.combo_provider)
        config_layout.addWidget(QLabel("Model:"))
        config_layout.addWidget(self.input_model)
        config_layout.addWidget(QLabel("URL:"))
        config_layout.addWidget(self.input_url)
        config_layout.addWidget(QLabel("Key:"))
        config_layout.addWidget(self.input_key)

        config_group.setLayout(config_layout)
        main_layout.addWidget(config_group)

        self.prompt_input = QTextEdit()
        self.prompt_input.setPlaceholderText("Describe the Python application you want to build...")
        self.prompt_input.setMaximumHeight(100)
        main_layout.addWidget(self.prompt_input)

        btn_layout = QHBoxLayout()
        self.btn_start = QPushButton("Start Build")
        self.btn_start.setStyleSheet("background-color: #007ACC; color: white; padding: 8px; font-weight: bold;")
        self.btn_start.clicked.connect(self.start_process)

        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setStyleSheet("background-color: #D32F2F; color: white; padding: 8px;")
        self.btn_stop.clicked.connect(self.stop_process)
        self.btn_stop.setEnabled(False)

        self.btn_save_as = QPushButton("Save As...")
        self.btn_save_as.setStyleSheet("background-color: #FF9800; color: white; padding: 8px;")
        self.btn_save_as.clicked.connect(self.save_as)

        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_stop)
        btn_layout.addWidget(self.btn_save_as)
        main_layout.addLayout(btn_layout)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.hide()
        main_layout.addWidget(self.progress_bar)

        splitter = QSplitter()

        log_group = QWidget()
        log_layout = QVBoxLayout(log_group)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.addWidget(QLabel("Build Log:"))
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet("background-color: #1E1E1E; color: #00FF00; font-family: Consolas; font-size: 12px;")
        log_layout.addWidget(self.log_view)
        splitter.addWidget(log_group)

        files_group = QWidget()
        files_layout = QVBoxLayout(files_group)
        files_layout.setContentsMargins(0, 0, 0, 0)
        self.file_tabs = QTabWidget()
        self.file_tabs.setTabsClosable(False)
        files_layout.addWidget(self.file_tabs)
        splitter.addWidget(files_group)

        splitter.setSizes([600, 600])
        main_layout.addWidget(splitter)

        self.toggle_inputs("Ollama")

    def toggle_inputs(self, text):
        if text == "Ollama":
            self.input_url.setEnabled(False)
            self.input_key.setEnabled(False)
            self.input_model.setText("qwen2.5:7b")
        else:
            self.input_url.setEnabled(True)
            self.input_url.setText("https://sia.sansol.in:9000/v1")
            self.input_key.setEnabled(True)
            self.input_key.setText("INTERNAL-LLM-TOKEN")
            self.input_model.setText("sia")

    def start_process(self):
        prompt = self.prompt_input.toPlainText().strip()
        if not prompt:
            QMessageBox.warning(self, "Input Error", "Please enter a prompt description.")
            return

        config = {
            "provider_type": self.combo_provider.currentText(),
            "model_name": self.input_model.text(),
            "api_url": self.input_url.text().strip() or None,
            "api_key": self.input_key.text().strip() or os.getenv("OPENAI_API_KEY", "")
        }

        self.log_view.clear()
        self.file_tabs.clear()
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.progress_bar.show()

        self.worker = StateMachineWorker(prompt, config)
        self.worker.log_signal.connect(self.log_view.append)
        self.worker.finished_signal.connect(self.process_finished)
        self.worker.command_signal.connect(self.handle_command_request)
        self.worker.start()

    def handle_command_request(self, cmd_json):
        cmd_data = json.loads(cmd_json)
        command = cmd_data["command"]
        description = cmd_data["description"]

        is_safe = any(command.strip().startswith(s) for s in self._safe_commands)
        if is_safe:
            self.worker.approve_command(True)
            return

        dialog = CommandApprovalDialog(command, description, self)
        result = dialog.exec()
        self.worker.approve_command(dialog.approved)

    def stop_process(self):
        if hasattr(self, 'worker'):
            self.worker.stop()
            self.log_view.append("\nStop signal sent...")

    def process_finished(self, success, message):
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress_bar.hide()

        if hasattr(self, 'worker') and self.worker._context is not None:
            self._update_file_tabs(self.worker._context.files)

        if success:
            QMessageBox.information(self, "Build Success", message)
        else:
            QMessageBox.warning(self, "Build Stopped", message)

    def _update_file_tabs(self, files):
        self.file_tabs.clear()
        for path, content in files.items():
            editor = QTextEdit()
            editor.setReadOnly(True)
            editor.setPlainText(content)
            editor.setStyleSheet("background-color: #1E1E1E; color: #DDD; font-family: Consolas; font-size: 12px;")
            self.file_tabs.addTab(editor, os.path.basename(path))

    def save_as(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Save Directory")
        if directory:
            if hasattr(self, 'worker') and self.worker._context is not None:
                for path, content in self.worker._context.files.items():
                    full_path = os.path.join(directory, path)
                    os.makedirs(os.path.dirname(full_path) if os.path.dirname(full_path) else directory, exist_ok=True)
                    with open(full_path, "w", encoding="utf-8") as f:
                        f.write(content)
                QMessageBox.information(self, "Saved", f"Project saved to {directory}")
            else:
                QMessageBox.warning(self, "No Project", "No project to save yet.")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
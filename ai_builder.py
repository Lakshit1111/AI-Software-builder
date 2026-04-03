import sys
import os
import subprocess
import json
import time
import tempfile
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import List, Dict, Optional

# Third-party imports
from openai import OpenAI
import ollama
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QTextEdit, QLabel, QPushButton, 
                               QLineEdit, QComboBox, QGroupBox, QProgressBar, QMessageBox)
from PySide6.QtCore import QThread, Signal, Slot
from dotenv import load_dotenv

# Load environment variables (Create a .env file with OPENAI_API_KEY if needed)
load_dotenv()

# ==========================================
# 1. DATA STRUCTURES (The "Blackboard")
# ==========================================

class State(Enum):
    """Defines the possible modes of the AI Agent."""
    INIT = auto()        # Startup
    ENHANCING = auto()
    PLANNING = auto()    # Architecting the solution
    CODING = auto()      # Writing code
    TESTING = auto()     # verifying code
    FIXING = auto()      # Debugging errors
    FINISHED = auto()    # Success
    FAILED = auto()      # Failure


def load_skills():
    try:
        with open("skills.md", "r", encoding="utf-8") as f:
            return f.read()
    except:
        return ""

skills = load_skills()

@dataclass
class ProjectContext:
    """
    The Single Source of Truth. 
    All agents read from here; only the Worker writes to here.
    """
    original_prompt: str = ""
    enhanced_prompt: str = ""
    plan: List[str] = field(default_factory=list)
    current_step_index: int = 0
    
    # Virtual File System: {'main.py': 'import sys...', 'utils.py': '...'}
    files: Dict[str, str] = field(default_factory=dict)
    
    # Execution State
    last_error: str = ""
    attempt_count: int = 0
    max_retries: int = 3
    
    def get_main_code(self):
        return self.files.get('main.py', "")

    def update_main_code(self, code):
        self.files['main.py'] = code

# ==========================================
# 2. BACKEND ABSTRACTION
# ==========================================

import requests
import ollama

class LLMProvider:
    """
    Wrapper to switch between:
    - vLLM (OpenAI-compatible REST API via requests)
    - Ollama (local)
    """

    def __init__(
        self,
        provider_type,
        model_name,
        api_url="https://sia.sansol.in:9000/v1",
        api_key="INTERNAL-LLM-TOKEN",
        verify_ssl=False,
        timeout=90
    ):
        self.provider_type = provider_type
        self.model_name = model_name
        self.api_url = api_url
        self.api_key = api_key
        self.verify_ssl = verify_ssl
        self.timeout = timeout

        if self.provider_type == "Ollama":
            self.client = ollama.Client(host="http://localhost:11434")

    # =====================================================
    # CHAT METHOD
    # =====================================================
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

    # =====================================================
    # vLLM (REQUESTS)
    # =====================================================
    def _chat_vllm(self, messages, temperature, system_prompt):
        url = f"{self.api_url.rstrip('/')}/chat/completions"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        final_messages = []
        if system_prompt:
            final_messages.append({
                "role": "system",
                "content": system_prompt
            })

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

    # =====================================================
    # OLLAMA
    # =====================================================
    def _chat_ollama(self, messages, temperature):
        response = self.client.chat(
            model=self.model_name,
            messages=messages,
            options={"temperature": temperature}
        )
        return response["message"]["content"]

# ==========================================
# 3. AGENT DEFINITIONS (The "Tools")
# ==========================================

class BaseAgent:
    def __init__(self, llm: LLMProvider):
        self.llm = llm

    def _clean_code(self, text):
        """Robust cleanup that handles 'chatty' models."""
        # 1. Try to find markdown blocks
        if "```python" in text:
            text = text.split("```python")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        
        # 2. Fallback: If no markdown, looks for the first import or def
        # (This prevents "Here is the code: import sys..." errors)
        else:
            lines = text.split('\n')
            clean_lines = []
            code_started = False
            for line in lines:
                # Simple heuristic to find start of code
                if line.strip().startswith(("import ", "from ", "def ", "class ", "#")):
                    code_started = True
                if code_started:
                    clean_lines.append(line)
            
            if clean_lines:
                text = "\n".join(clean_lines)

        return text.strip()


class PromptEnhancer(BaseAgent):
    def enhance(self, user_prompt):
        system_prompt = ("""

            {skills}

            [ROLE: ENHANSER]
            You are an Expert Product Manager and Requirements Engineer.
            Your job is to take a brief user request for a software application and expand it into a comprehensive, unambiguous technical prompt. 
            \n\nStrict Rules:
            \n1. Identify the core functionality, necessary UI/CLI components, and edge cases.
            \n2. If it is a GUI application, explicitly specify its structure in detail.
            \n3. Detail the expected behavior (e.g., 'Input fields must clear after submission', 'Errors must be caught and displayed safely').
            \n4. Do not write code. Do not write the implementation steps.
            \n5. Output ONLY the enhanced, detailed project description. No conversational intro.

            """
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Brief Request: {user_prompt}\n\nPlease provide the enhanced technical description."}
        ]
        
        return self.llm.chat(messages, temperature=0.2)



class Planner(BaseAgent):
    def create_plan(self, user_prompt):
        system_prompt = f"""
            {skills}

            [ROLE: Planner]

            You are responsible for breaking down a project into clear, executable steps.

            Focus:
            - Convert the project into 4–6 concrete implementation steps
            - Each step must produce a meaningful code change
            - Steps must be ordered logically and build on each other

            Output Rules:
            - Return ONLY a numbered list
            - No explanations
            - No markdown
        """

        example_prompt = (
            "User: Build a basic request tracker app.\n"
            "Plan:\n"
            "1. Initialize the project structure and main application entry point.\n"
            "2. Implement the user interface for submitting and viewing requests.\n"
            "3. Add a data storage mechanism for persisting requests.\n"
            "4. Implement logic to create, retrieve, and display requests.\n"
            "5. Add validation and error handling for user inputs.\n"
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Example:\n{example_prompt}\n\nReal Task: {user_prompt}"}
        ]
        
        return self.llm.chat(messages, temperature=0.1)

class Developer(BaseAgent):
    def write_code(self, task, context: ProjectContext):
        system_prompt = f"""
            {skills}

            [ROLE: Developer]

            You are responsible for implementing the given task into the existing codebase.

            Focus:
            - Modify the code to complete the current task
            - Maintain compatibility with existing functionality
            - Ensure the application remains runnable after changes

            Output Rules:
            - Return ONLY the full updated Python code for main.py
            - No explanations
            - No markdown
        """
        
        user_msg = f"""
        Overall Project Goal: {context.original_prompt}
        
        Current Task: {task}
        
        Current File Content (main.py):
        {context.get_main_code() if context.get_main_code() else "# New File"}
        """
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg}
        ]
        response = self.llm.chat(messages, temperature=0.1)
        return self._clean_code(response)

    def fix_code(self, context: ProjectContext):
        system_prompt = f"""
            {skills}

            [ROLE: Debugger]

            You are responsible for fixing errors in an existing Python codebase.

            Focus:
            - Identify the root cause of the error
            - Modify the code to resolve the issue
            - Preserve all working functionality

            Output Rules:
            - Return ONLY the full corrected Python code for main.py
            - No explanations
            - No markdown
        """
        
        user_msg = f"""
        The code failed with this error:
        {context.last_error}

        Current Code:
        {context.get_main_code()}
        
        Task: Fix the error and return the full code.
        """
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg}
        ]
        response = self.llm.chat(messages, temperature=0.1)
        return self._clean_code(response)

# ==========================================
# 4. STATE MACHINE WORKER (The "Brain")
# ==========================================

class StateMachineWorker(QThread):
    log_signal = Signal(str)
    finished_signal = Signal(bool, str) # success, message

    def __init__(self, user_prompt, config):
        super().__init__()
        self.user_prompt = user_prompt
        self.config = config
        self.is_running = True

    def run(self):
        self.log("🚀 Initializing AI State Machine...")
        
        # 1. Setup Backend
        try:
            llm = LLMProvider(
                self.config['provider_type'],
                self.config['model_name']
            )
            enhancer = PromptEnhancer(llm)
            planner = Planner(llm)
            developer = Developer(llm)
        except Exception as e:
            self.finished_signal.emit(False, f"Setup Error: {e}")
            return

        # 2. Initialize State
        context = ProjectContext(original_prompt=self.user_prompt)
        current_state = State.INIT
        
        # 3. The Loop
        while self.is_running and current_state not in [State.FINISHED, State.FAILED]:
            
            # --- STATE: INIT ---
            if current_state == State.INIT:
                self.log(f"🔄 State: {current_state.name}")
                current_state = State.ENHANCING

            elif current_state == State.ENHANCING:
                self.log(f"🧠 State: {current_state.name} - enhancing prompt")
                context.original_prompt = enhancer.enhance(context.original_prompt)
                self.log(f"Enhanced generated prompt \n{context.original_prompt}")

                current_state = State.PLANNING

            # --- STATE: PLANNING ---
            elif current_state == State.PLANNING:
                self.log(f"🧠 State: {current_state.name} - Architecting solution...")
                raw_plan = planner.create_plan(context.original_prompt)
                
                # Parse plan (simple split by newline)
                context.plan = [line.strip() for line in raw_plan.split('\n') if line.strip() and (line[0].isdigit() or line.startswith('-'))]
                
                if not context.plan:
                    context.plan = [context.original_prompt] # Fallback
                
                self.log(f"📋 Plan generated with {len(context.plan)} steps.")
                for step in context.plan:
                    self.log(f"  - {step}")
                    
                current_state = State.CODING

            # --- STATE: CODING ---
            elif current_state == State.CODING:
                if context.current_step_index >= len(context.plan):
                    current_state = State.FINISHED
                    continue

                step_desc = context.plan[context.current_step_index]
                self.log(f"\n👨‍💻 State: {current_state.name} - Working on Step {context.current_step_index + 1}/{len(context.plan)}")
                self.log(f"   Task: {step_desc}")
                
                new_code = developer.write_code(step_desc, context)
                context.update_main_code(new_code)
                
                current_state = State.TESTING

            # --- STATE: TESTING ---
            elif current_state == State.TESTING:
                self.log(f"🧪 State: {current_state.name} - Verifying code integrity...")
                error = self.run_code_safely(context.get_main_code())
                
                if error:
                    self.log(f"❌ Test Failed: {error}")
                    context.last_error = error
                    current_state = State.FIXING
                else:
                    self.log("✅ Test Passed.")
                    context.attempt_count = 0
                    context.current_step_index += 1
                    
                    # Check if done
                    if context.current_step_index >= len(context.plan):
                        current_state = State.FINISHED
                    else:
                        current_state = State.CODING

            # --- STATE: FIXING ---
            elif current_state == State.FIXING:
                if context.attempt_count >= context.max_retries:
                    self.log("⚠️ State: FIXING - Max retries reached. Moving to next step with broken code.")
                    context.attempt_count = 0
                    context.current_step_index += 1
                    current_state = State.Failed
                else:
                    context.attempt_count += 1
                    self.log(f"🔧 State: FIXING - Attempt {context.attempt_count}/{context.max_retries}")
                    fixed_code = developer.fix_code(context)
                    context.update_main_code(fixed_code)
                    current_state = State.TESTING

        # 4. Finalization
        if current_state == State.FINISHED:
            self.save_project(context)
            self.log("\n✨ Project Build Complete!")
            self.finished_signal.emit(True, "Project saved to 'generated_app' folder.")
        elif not self.is_running:
             self.finished_signal.emit(False, "Process stopped by user.")
        else:
            self.finished_signal.emit(False, "Build Failed.")

    def run_code_safely(self, code):
        """
        Runs code in a temporary file to check for runtime errors.
        """
        # --- FIX: Detect GUI frameworks ---
        is_gui = "PySide6" in code or "PyQt" in code or "tkinter" in code
        
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as tmp:
                tmp.write(code)
                tmp_path = tmp.name

            # Execute
            result = subprocess.run(
                [sys.executable, tmp_path],
                capture_output=True,
                text=True,
                timeout=5  # Keep timeout short
            )
            
            os.unlink(tmp_path) 

            if result.returncode != 0:
                return result.stderr.strip()
            return None 

        except subprocess.TimeoutExpired:
            os.unlink(tmp_path) 
            # --- FIX: If it's a GUI app, a timeout is actually GOOD (it means the window stayed open) ---
            if is_gui:
                return None 
            return "Execution Timed Out (Possible infinite loop)"
            
        except Exception as e:
            return str(e)

    def save_project(self, context):
        os.makedirs("generated_app", exist_ok=True)
        with open("generated_app/main.py", "w", encoding="utf-8") as f:
            f.write(context.get_main_code())
        
        with open("generated_app/build_log.json", "w", encoding="utf-8") as f:
            json.dump({"plan": context.plan, "steps_completed": context.current_step_index}, f, indent=2)

    def log(self, msg):
        self.log_signal.emit(msg)

    def stop(self):
        self.is_running = False

# ==========================================
# 5. UI IMPLEMENTATION
# ==========================================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Cognitive AI State Machine Builder")
        self.resize(1100, 850)
        self.setup_ui()

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # Header
        header = QLabel("🤖 Cognitive AI Builder (State Machine Architecture)")
        header.setStyleSheet("font-size: 18px; font-weight: bold; color: #4CAF50;")
        main_layout.addWidget(header)

        # Config Section
        config_group = QGroupBox("LLM Configuration")
        config_layout = QHBoxLayout()
        
        self.combo_provider = QComboBox()
        self.combo_provider.addItems(["Ollama", "vLLM / OpenAI"])
        self.combo_provider.currentTextChanged.connect(self.toggle_inputs)
        
        self.input_model = QLineEdit("qwen2.5:7b")
        self.input_url = QLineEdit()
        self.input_key = QLineEdit()
        self.input_key.setEchoMode(QLineEdit.Password)
        
        config_layout.addWidget(QLabel("Provider:"))
        config_layout.addWidget(self.combo_provider)
        config_layout.addWidget(QLabel("Model:"))
        config_layout.addWidget(self.input_model)
        # config_layout.addWidget(QLabel("URL:"))
        # config_layout.addWidget(self.input_url)
        # config_layout.addWidget(QLabel("Key:"))
        # config_layout.addWidget(self.input_key)
        
        config_group.setLayout(config_layout)
        main_layout.addWidget(config_group)

        # Input Section
        self.prompt_input = QTextEdit()
        self.prompt_input.setPlaceholderText("Describe the Python application you want to build (e.g., 'A request tracker app using SQLite')...")
        self.prompt_input.setMaximumHeight(100)
        main_layout.addWidget(self.prompt_input)

        # Controls
        btn_layout = QHBoxLayout()
        self.btn_start = QPushButton("🚀 Start Build")
        self.btn_start.setStyleSheet("background-color: #007ACC; color: white; padding: 8px; font-weight: bold;")
        self.btn_start.clicked.connect(self.start_process)
        
        self.btn_stop = QPushButton("🛑 Stop")
        self.btn_stop.setStyleSheet("background-color: #D32F2F; color: white; padding: 8px;")
        self.btn_stop.clicked.connect(self.stop_process)
        self.btn_stop.setEnabled(False)

        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_stop)
        main_layout.addLayout(btn_layout)

        # Progress & Logs
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0) # Indeterminate initially
        self.progress_bar.hide()
        main_layout.addWidget(self.progress_bar)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet("""
            background-color: #1E1E1E; 
            color: #00FF00; 
            font-family: Consolas; 
            font-size: 13px;
        """)
        main_layout.addWidget(self.log_view)
        
        self.toggle_inputs("Ollama")

    def toggle_inputs(self, text):
        if text == "Ollama":
            self.input_url.setPlaceholderText("http://localhost:11434 (Default)")
            self.input_url.setText("")
            self.input_key.setEnabled(False)
            self.input_model.setText("qwen2.5:7b")
        else:
            self.input_url.setPlaceholderText("https://api.openai.com/v1")
            self.input_url.setText("")
            self.input_key.setEnabled(True)
            self.input_model.setText("sia")

    def start_process(self):
        prompt = self.prompt_input.toPlainText().strip()
        if not prompt:
            QMessageBox.warning(self, "Input Error", "Please enter a prompt description.")
            return

        config = {
            "provider_type": self.combo_provider.currentText(),
            "model_name": self.input_model.text(),
            "api_url": self.input_url.text() if self.input_url.text() else None,
            "api_key": self.input_key.text() if self.input_key.text() else "EMPTY"
        }

        self.log_view.clear()
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.progress_bar.show()

        self.worker = StateMachineWorker(prompt, config)
        self.worker.log_signal.connect(self.log_view.append)
        self.worker.finished_signal.connect(self.process_finished)
        self.worker.start()

    def stop_process(self):
        if hasattr(self, 'worker'):
            self.worker.stop()
            self.log_view.append("\n🛑 Stop signal sent...")

    def process_finished(self, success, message):
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress_bar.hide()
        
        if success:
            QMessageBox.information(self, "Build Success", message)
        else:
            QMessageBox.warning(self, "Build Stopped", message)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
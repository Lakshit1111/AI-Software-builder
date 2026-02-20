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
    PLANNING = auto()    # Architecting the solution
    CODING = auto()      # Writing code
    TESTING = auto()     # verifying code
    FIXING = auto()      # Debugging errors
    FINISHED = auto()    # Success
    FAILED = auto()      # Failure

@dataclass
class ProjectContext:
    """
    The Single Source of Truth. 
    All agents read from here; only the Worker writes to here.
    """
    original_prompt: str = ""
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

class LLMProvider:
    """Wrapper to switch between Ollama (Local) and OpenAI/vLLM (Remote)."""
    def __init__(self, provider_type, model_name, api_url=None, api_key="EMPTY"):
        self.provider_type = provider_type
        self.model_name = model_name
        self.api_url = api_url
        self.api_key = api_key
        
        if self.provider_type == "vLLM / OpenAI":
            self.client = OpenAI(base_url=self.api_url, api_key=self.api_key)
        elif self.provider_type == "Ollama":
            # Initialize Ollama client
            self.client = ollama.Client(host=self.api_url) if self.api_url else ollama

    def chat(self, messages, temperature=0.7):
        try:
            if self.provider_type == "vLLM / OpenAI":
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    temperature=temperature
                )
                return response.choices[0].message.content

            elif self.provider_type == "Ollama":
                response = self.client.chat(
                    model=self.model_name,
                    messages=messages,
                    options={'temperature': temperature}
                )
                return response['message']['content']
                
        except Exception as e:
            return f"API_ERROR: {str(e)}"

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
class Planner(BaseAgent):
    def create_plan(self, user_prompt):
        system_prompt = (
            "You are a Senior Technical Lead. "
            "Your goal is to break down a project into 3-5 specific, actionable implementation tasks. "
            "Each task must be a single, self-contained coding job."
            "\n\n"
            "Rules:"
            "\n1. Do NOT use generic steps like 'Test' or 'Design'. The testing is automated."
            "\n2. Step 1 must always be 'Initialize the basic project structure and main window'."
            "\n3. Subsequent steps must add specific features (e.g., 'Add math logic', 'Add history feature')."
            "\n4. Return ONLY a numbered list. No intro, no markdown."
        )
        
        # We give it a "One-Shot" example to teach it the format
        example_prompt = (
            "User: Build a calculator.\n"
            "Plan:\n"
            "1. Create a PyQt6 main window with a display widget.\n"
            "2. Implement the grid layout with number buttons (0-9).\n"
            "3. Implement the operator buttons (+, -, *, /) and connect signals.\n"
            "4. Implement the '=' logic to evaluate the expression safely.\n"
            "5. Add a 'Clear' button to reset the display."
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Example:\n{example_prompt}\n\nReal Task: {user_prompt}"}
        ]
        
        return self.llm.chat(messages, temperature=0.2)

class Developer(BaseAgent):
    def write_code(self, task, context: ProjectContext):
        system_prompt = (
            "You are an expert Python Developer. "
            "Your goal is to implement the requested task into the existing code base. "
            "Return the FULL valid Python code for 'main.py' including imports."
        )
        
        user_msg = f"""
        Current File Content (main.py):
        {context.get_main_code() if context.get_main_code() else "# New File"}

        Current Task: {task}
        
        Instructions:
        1. Implement the feature described in the task.
        2. Ensure all imports are at the top.
        3. Return the complete file content.
        4. Understand the user intent and task.
        """
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg}
        ]
        response = self.llm.chat(messages, temperature=0.4)
        return self._clean_code(response)

    def fix_code(self, context: ProjectContext):
        system_prompt = (
            "You are a Senior Debugging Engineer. "
            "Analyze the error message and the current code. "
            "Fix the bug and return the FULL corrected Python code."
        )
        
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
        response = self.llm.chat(messages, temperature=0.2)
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
                self.config['model_name'],
                self.config['api_url'],
                self.config['api_key']
            )
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
                    current_state = State.CODING
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
        
        self.input_model = QLineEdit("llama3:latest")
        self.input_url = QLineEdit()
        self.input_key = QLineEdit()
        self.input_key.setEchoMode(QLineEdit.Password)
        
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
            self.input_model.setText("llama3:latest")
        else:
            self.input_url.setPlaceholderText("https://api.openai.com/v1")
            self.input_url.setText("")
            self.input_key.setEnabled(True)
            self.input_model.setText("gpt-4o-mini")

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
import sys
import os
import subprocess
import re
from openai import OpenAI
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QTextEdit, QLabel, QPushButton, 
                               QProgressBar, QMessageBox, QLineEdit, QSplitter)
from PySide6.QtCore import QThread, Signal, Qt
from  dotenv import load_dotenv

load_dotenv()


# --- CONFIGURATION ---
VLLM_API_URL = os.getenv("VLLM_API_URL")
VLLM_API_KEY = "EMPTY" 
MODEL_NAME = os.getenv("MODEL_NAME") # Ensure this matches your loaded model

class Agent:
    def __init__(self, name, role_prompt, client):
        self.name = name
        self.role_prompt = role_prompt
        self.client = client

    def think(self, user_input, context="", history=None):
        """
        Cognitive Step: The agent captures 'Thoughts' before 'Actions'.
        """
        # Base instructions for cognitive ability
        cognitive_instructions = (
            "You are a cognitive AI. You must think before you answer.\n"
            "Format your response exactly like this:\n"
            "THOUGHT: [Your internal reasoning about the task]\n"
            "RESPONSE: [Your final output or code]\n"
        )
        
        full_system_prompt = f"{self.role_prompt}\n{cognitive_instructions}"
        
        messages = [{"role": "system", "content": full_system_prompt}]
        
        if history:
            messages.extend(history)
            
        messages.append({"role": "user", "content": f"Context:\n{context}\n\nTask:\n{user_input}"})

        try:
            response = self.client.chat.completions.create(
                model=MODEL_NAME, messages=messages, temperature=0.5
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"THOUGHT: System Error\nRESPONSE: Error: {str(e)}"

    def extract_response(self, text):
        """Parses out the actual response, ignoring the internal thought process."""
        if "RESPONSE:" in text:
            return text.split("RESPONSE:")[-1].strip()
        return text

class BuilderWorker(QThread):
    log_signal = Signal(str)
    result_signal = Signal(str)
    finished_signal = Signal()

    def __init__(self, user_prompt):
        super().__init__()
        self.user_prompt = user_prompt
        self.client = OpenAI(base_url=VLLM_API_URL, api_key=VLLM_API_KEY)
        self.current_code = ""

    def run(self):
        self.log("--- Starting Cognitive AI Builder ---")
        
        # 1. Initialize Agents
        planner = Agent("Planner", "You are a Lead Architect. Break the project into 3-5 logical implementation steps. Return ONLY a numbered list.", self.client)
        developer = Agent("Developer", "You are a Senior Python Developer. Implement the code for the specific step requested. Integrate it into the existing code.", self.client)
        tester = Agent("Tester", "You are a QA Engineer. You analyze execution errors.", self.client)
        
        # 2. Planning Phase
        self.log(f"🧠 [Planner] Deconstructing request: '{self.user_prompt}'...")
        raw_plan = planner.think(self.user_prompt)
        plan_steps = self.parse_plan(planner.extract_response(raw_plan))
        
        self.log(f"📋 [Planner] Strategy: {plan_steps}")

        # 3. Iterative Development Loop
        self.current_code = "# Project Started\n"
        
        for i, step in enumerate(plan_steps):
            self.log(f"\n🚀 [Step {i+1}/{len(plan_steps)}] Implementing: {step}")
            
            # Developer thinks and codes
            dev_prompt = f"Current Code:\n{self.current_code}\n\nTask: Implement this step: '{step}'. Return the FULL updated code."
            raw_dev = developer.think(dev_prompt)
            new_code = self.clean_code(developer.extract_response(raw_dev))
            
            # Validation Loop (Run -> Fix -> Run)
            self.current_code = self.validate_and_fix(new_code, tester, developer)
        
        # Final Save
        self.save_code(self.current_code)
        self.result_signal.emit("Success")
        self.finished_signal.emit()

    def validate_and_fix(self, code, tester, developer):
        """The 'Terminal' Logic: Runs code and loops if it crashes."""
        attempts = 0
        max_retries = 3
        
        while attempts < max_retries:
            self.log(f"⚡ [Tester] Executing code in terminal (Attempt {attempts+1})...")
            
            # --- REAL TERMINAL EXECUTION ---
            error_output = self.run_in_terminal(code)
            
            if not error_output:
                self.log("✅ [Tester] Execution Successful (Exit Code 0).")
                return code
            else:
                self.log(f"❌ [Tester] Runtime Error:\n{error_output}")
                
                # Cognitive Fix
                fix_prompt = f"The code failed with this error:\n{error_output}\n\nFix the code."
                self.log("🔧 [Developer] Analyzing error and refactoring...")
                raw_fix = developer.think(fix_prompt, context=code)
                code = self.clean_code(developer.extract_response(raw_fix))
                attempts += 1

        self.log("⚠️ [System] Max retries reached. Proceeding with potential risks.")
        return code

    def run_in_terminal(self, code):
        """Writes code to a temp file and runs it via subprocess."""
        temp_file = "generated_app/temp_exec.py"
        with open(temp_file, "w") as f:
            f.write(code)
        
        try:
            # Capture both stdout and stderr
            result = subprocess.run(
                [sys.executable, temp_file],
                capture_output=True,
                text=True,
                timeout=5 # Timeout to prevent infinite loops
            )
            if result.returncode != 0:
                return result.stderr # Return the error message
            return None # No error
        except subprocess.TimeoutExpired:
            return None
        except Exception as e:
            return str(e)

    def parse_plan(self, plan_text):
        """Extracts numbered lines into a list."""
        lines = plan_text.split('\n')
        steps = [line.strip() for line in lines if line.strip() and (line[0].isdigit() or line.startswith('-'))]
        return steps if steps else [plan_text]

    def clean_code(self, text):
        """Removes Markdown and extra text."""
        if "```python" in text:
            text = text.split("```python")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        return text.strip()

    def log(self, message):
        self.log_signal.emit(message)

    def save_code(self, code):
        with open("generated_app/generated_project.py", "w") as f:
            f.write(code)

# --- UI CLASS (Unchanged mostly, just darker theme for 'Hacker' feel) ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Cognitive AI Builder")
        self.resize(900, 700)
        self.setup_ui()

    def setup_ui(self):
        # ... (Similar setup to previous, just standard PySide6 boilerplate) ...
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        
        self.prompt = QLineEdit()
        self.prompt.setPlaceholderText("Enter project description...")
        self.btn = QPushButton("Initialize Agents")
        self.btn.clicked.connect(self.start)
        
        layout.addWidget(self.prompt)
        layout.addWidget(self.btn)
        
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet("background-color: black; color: #00FF00; font-family: Consolas;")
        layout.addWidget(self.log_view)

    def start(self):
        self.worker = BuilderWorker(self.prompt.text())
        self.worker.log_signal.connect(self.log_view.append)
        self.worker.start()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
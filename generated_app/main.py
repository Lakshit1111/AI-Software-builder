# main.py

import tkinter as tk
from tkinter import messagebox

class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        
        # Set up the window title and size
        self.title("Basic Project Structure")
        self.geometry("400x350")
        
        # Create a label widget
        label = tk.Label(self, text="Welcome to the Basic Project Structure!")
        label.pack(pady=20)
        
        # Add input fields for arithmetic operations
        frame = tk.Frame(self)
        frame.pack()
        
        tk.Label(frame, text="Number 1:").pack(side=tk.LEFT, padx=5)
        self.num1_entry = tk.Entry(frame)
        self.num1_entry.pack(side=tk.LEFT, padx=5)
        
        operator_frame = tk.Frame(self)
        operator_frame.pack()
        
        # Define the variable for the radio buttons
        self.operator_var = tk.StringVar(value="+")
        
        operators = ["+", "-", "*", "/"]
        for op in operators:
            btn = tk.Radiobutton(operator_frame, text=op, variable=self.operator_var, value=op)
            btn.pack(side=tk.LEFT, padx=5)
        
        frame = tk.Frame(self)
        frame.pack()
        
        tk.Label(frame, text="Number 2:").pack(side=tk.LEFT, padx=5)
        self.num2_entry = tk.Entry(frame)
        self.num2_entry.pack(side=tk.LEFT, padx=5)
        
        # Add a button to perform the arithmetic operation
        calculate_button = tk.Button(self, text="Calculate", command=self.calculate_result)
        calculate_button.pack(pady=10)
        
        # Label to display the result
        self.result_label = tk.Label(self, text="")
        self.result_label.pack(pady=20)
        
        # History list to store previous results
        self.history = []
    
    def calculate_result(self):
        try:
            num1 = float(self.num1_entry.get())
            num2 = float(self.num2_entry.get())
            operator = self.operator_var.get()
            
            if operator == "+":
                result = num1 + num2
            elif operator == "-":
                result = num1 - num2
            elif operator == "*":
                result = num1 * num2
            elif operator == "/":
                result = num1 / num2
            
            self.result_label.config(text=f"Result: {result}")
            
            # Add the calculation to the history list
            self.history.append(f"{num1} {operator} {num2} = {result}")
        
        except ValueError:
            messagebox.showerror("Error", "Please enter valid numbers.")
        except ZeroDivisionError:
            messagebox.showerror("Error", "Cannot divide by zero.")
    
    def display_history(self):
        history_text = "\n".join(self.history)
        messagebox.showinfo("Calculation History", f"History:\n{history_text}")

if __name__ == "__main__":
    app = MainWindow()
    
    # Add a button to display the history
    history_button = tk.Button(app, text="Show History", command=app.display_history)
    history_button.pack(pady=10)
    
    app.mainloop()
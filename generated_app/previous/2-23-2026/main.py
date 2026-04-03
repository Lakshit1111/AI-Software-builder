import tkinter as tk
from tkinter import ttk

class CalculatorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        
        self.title("Calculator")
        self.geometry("400x600")
        
        self.init_ui()

    def init_ui(self):
        """
        Initialize the user interface for a calculator using a Grid layout manager.
        """
        # Create main frame
        main_frame = ttk.Frame(self, padding="10")
        main_frame.grid(column=0, row=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid columns and rows for expansion
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        main_frame.columnconfigure(list(range(4)), weight=1)  # 4 columns for digits and operators
        main_frame.rowconfigure(list(range(5)), weight=1)     # 5 rows including display

        # Entry field to show the input and result
        self.entry = ttk.Entry(main_frame, font=('Arial', 20), width=15)
        self.entry.grid(column=0, row=0, columnspan=4, pady=(10, 0))

        # Digit buttons
        digits = [
            ('7', 1, 0),
            ('8', 1, 1),
            ('9', 1, 2),
            ('4', 2, 0),
            ('5', 2, 1),
            ('6', 2, 2),
            ('1', 3, 0),
            ('2', 3, 1),
            ('3', 3, 2),
            ('0', 4, 1)
        ]
        
        for (digit, row, col) in digits:
            button = ttk.Button(main_frame, text=digit, command=lambda d= digit: self.on_digit(d))
            button.grid(column=col, row=row, padx=5, pady=5)

        # Operator buttons
        operators = [
            ('+', 1, 3),
            ('-', 2, 3),
            ('*', 3, 3),
            ('/', 4, 3)
        ]
        
        for (operator, row, col) in operators:
            button = ttk.Button(main_frame, text=operator, command=lambda o=operator: self.on_operator(o))
            button.grid(column=col, row=row, padx=5, pady=5)

        # Clear and Equal buttons
        clear_button = ttk.Button(main_frame, text='C', command=self.clear)
        clear_button.grid(column=0, row=4, columnspan=2, padx=5, pady=5)

        equal_button = ttk.Button(main_frame, text='=', command=self.calculate)
        equal_button.grid(column=3, row=4, columnspan=2, padx=5, pady=5)

    def on_digit(self, digit):
        current_text = self.entry.get()
        self.entry.delete(0, tk.END)
        self.entry.insert(tk.END, current_text + str(digit))

    def on_operator(self, operator):
        current_text = self.entry.get()
        if current_text and current_text[-1] not in '+-*/':
            self.entry.delete(len(current_text) - 1, tk.END)
        self.entry.insert(tk.END, operator)

    def clear(self):
        self.entry.delete(0, tk.END)

    def calculate(self):
        try:
            result = eval(self.entry.get())
            self.entry.delete(0, tk.END)
            self.entry.insert(tk.END, str(result))
        except Exception as e:
            self.entry.delete(0, tk.END)
            self.entry.insert(tk.END, "Error")

    def perform_arithmetic_operation(self, operator, num1, num2):
        if operator == '+':
            return num1 + num2
        elif operator == '-':
            return num1 - num2
        elif operator == '*':
            return num1 * num2
        elif operator == '/':
            try:
                return num1 / num2
            except ZeroDivisionError:
                return "Error: Division by zero"
        else:
            return "Invalid operation"

    def on_operation(self, operator):
        current_text = self.entry.get()
        if current_text and current_text[-1] not in '+-*/':
            try:
                num1 = float(current_text)
                self.entry.delete(0, tk.END)
                self.entry.insert(tk.END, str(num1) + operator)
            except ValueError:
                self.entry.delete(0, tk.END)
                self.entry.insert(tk.END, "Error")

    def calculate_result(self):
        try:
            expression = self.entry.get()
            if '+' in expression or '-' in expression or '*' in expression or '/' in expression:
                parts = expression.split()
                num1 = float(parts[0])
                operator = parts[1]
                num2 = float(parts[-1])
                result = self.perform_arithmetic_operation(operator, num1, num2)
                self.entry.delete(0, tk.END)
                self.entry.insert(tk.END, str(result))
            else:
                self.entry.delete(0, tk.END)
                self.entry.insert(tk.END, "Invalid expression")
        except Exception as e:
            self.entry.delete(0, tk.END)
            self.entry.insert(tk.END, "Error")

    def on_operation_button(self):
        try:
            current_text = self.entry.get()
            if current_text and current_text[-1] not in '+-*/':
                num1 = float(current_text)
                operator = self.entry.get().split()[-1]
                num2 = float(input("Enter the second number: "))
                result = self.perform_arithmetic_operation(operator, num1, num2)
                self.entry.delete(0, tk.END)
                self.entry.insert(tk.END, str(result))
            else:
                self.entry.delete(0, tk.END)
                self.entry.insert(tk.END, "Invalid expression")
        except ValueError:
            self.entry.delete(0, tk.END)
            self.entry.insert(tk.END, "Error: Invalid input")

if __name__ == "__main__":
    app = CalculatorApp()
    # Add a new button for performing operations
    operation_button = ttk.Button(app, text='Calculate', command=app.on_operation_button)
    operation_button.grid(column=2, row=4, columnspan=2, padx=5, pady=5)
    
    app.mainloop()
import os
import tkinter as tk
from calculator import add, subtract, multiply, divide

class CalculatorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Simple Calculator")
        
        # Ensure the calculator is placed at the top of the main window
        self.root.geometry("+0+0")  # Position the window at the top-left corner
        
        # Create a frame for the display and buttons
        frame = tk.Frame(root)
        frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        # Create a read-only text field for displaying the current input and results
        self.display = tk.Entry(frame, width=40, borderwidth=5, state='readonly')
        self.display.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)
        
        buttons_frame = tk.Frame(frame)
        buttons_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        buttons = [
            ('7', 0, 0), ('8', 0, 1), ('9', 0, 2), ('/', 0, 3),
            ('4', 1, 0), ('5', 1, 1), ('6', 1, 2), ('*', 1, 3),
            ('1', 2, 0), ('2', 2, 1), ('3', 2, 2), ('-', 2, 3),
            ('0', 3, 0), ('.', 3, 1), ('=', 3, 2), ('+', 3, 3),
            ('C', 4, 0), ('DEL', 4, 1), ('%', 4, 2), ('^', 4, 3),
        ]
        
        for (text, row, col) in buttons:
            button = tk.Button(buttons_frame, text=text, width=10, height=3, command=lambda t=text: self.on_button_click(t))
            button.grid(row=row, column=col)
        
        # Add a horizontal frame for the bottom buttons
        bottom_frame = tk.Frame(root)
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Add buttons to the bottom frame
        bottom_buttons = [
            ('History', 0, 0), ('Button2', 0, 1), ('Button3', 0, 2), ('Button4', 0, 3)
        ]
        
        for (text, row, col) in bottom_buttons:
            button = tk.Button(bottom_frame, text=text, width=10, height=3, command=lambda t=text: self.on_bottom_button_click(t))
            button.grid(row=row, column=col, sticky=tk.W+tk.E)
        
        # Initialize history
        self.history = []

        # Create a dropdown menu
        self.dropdown_var = tk.StringVar(root)
        self.dropdown_var.set("Option 1")  # default value
        options = ["Option 1", "Option 2", "Option 3"]
        self.dropdown_menu = tk.OptionMenu(root, self.dropdown_var, *options)
        self.dropdown_menu.pack(side=tk.BOTTOM, fill=tk.X)

        # Add theme options
        self.theme_var = tk.StringVar(root)
        self.theme_var.set("Light")  # default value
        themes = ["Light", "Dark"]
        self.theme_menu = tk.OptionMenu(root, self.theme_var, *themes, command=self.change_theme)
        self.theme_menu.pack(side=tk.BOTTOM, fill=tk.X)

    def on_button_click(self, value):
        try:
            if value == '=':
                result = self.evaluate_expression(self.display.get())
                self.update_display(f"Result: {result}")
                self.history.append(f"{self.display.get()} = {result}")
                self.update_dropdown()
            elif value == 'C':
                self.update_display('')
            elif value == 'DEL':
                current_text = self.display.get()
                new_text = current_text[:-1]
                self.update_display(new_text)
            else:
                current_text = self.display.get()
                new_text = current_text + value
                self.update_display(new_text)
        except ZeroDivisionError:
            self.update_display("Error: Division by zero")
        except Exception as e:
            self.update_display(f"Error: {str(e)}")

    def on_bottom_button_click(self, value):
        if value == 'History':
            self.show_history()
        elif value == 'Button2':
            self.update_display("Button2 clicked")
        elif value == 'Button3':
            self.update_display("Button3 clicked")
        elif value == 'Button4':
            self.update_display("Button4 clicked")

    def update_display(self, text):
        self.display.config(state='normal')
        self.display.delete(0, tk.END)
        self.display.insert(0, text)
        self.display.config(state='readonly')

    def evaluate_expression(self, expression):
        # Replace '^' with '**' for exponentiation
        expression = expression.replace('^', '**')
        # Evaluate the expression using the built-in eval function
        return eval(expression)

    def show_history(self):
        history_window = tk.Toplevel(self.root)
        history_window.title("Calculation History")
        
        history_text = tk.Text(history_window, width=40, height=20)
        history_text.pack(padx=10, pady=10)
        
        for entry in self.history:
            history_text.insert(tk.END, entry + "\n")

    def update_dropdown(self):
        # Limit history to the last 10 entries
        if len(self.history) > 10:
            self.history = self.history[-10:]
        
        # Update the dropdown menu options
        self.dropdown_menu['menu'].delete(0, 'end')
        for entry in reversed(self.history):
            self.dropdown_menu['menu'].add_command(label=entry, command=tk._setit(self.dropdown_var, entry))

    def change_theme(self, theme):
        if theme == "Light":
            self.root.configure(bg="white")
            self.display.configure(bg="white", fg="black")
        elif theme == "Dark":
            self.root.configure(bg="black")
            self.display.configure(bg="black", fg="white")

def create_project_directory():
    project_dir = "calculator_project"
    if not os.path.exists(project_dir):
        os.makedirs(project_dir)

if __name__ == "__main__":
    create_project_directory()
    root = tk.Tk()
    app = CalculatorApp(root)
    root.mainloop()
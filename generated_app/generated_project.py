import tkinter as tk
from tkinter import ttk

class Calculator:
    def __init__(self, master):
        self.master = master
        master.title("Calculator")

        self.display = tk.Entry(master, width=25, font=('Arial', 16))
        self.display.grid(row=0, column=0, columnspan=4, padx=10, pady=10)

        # Define buttons
        buttons = [
            ("7", 1, 0), ("8", 1, 1), ("9", 1, 2), ("/", 1, 3),
            ("4", 2, 0), ("5", 2, 1), ("6", 2, 2), ("*", 2, 3),
            ("1", 3, 0), ("2", 3, 1), ("3", 3, 2), ("-", 3, 3),
            ("0", 4, 0), (".", 4, 1), ("=", 4, 2), ("+", 4, 3)
        ]

        for (text, row, col) in buttons:
            button = ttk.Button(master, text=text, width=5, command=lambda t=text: self.button_click(t))
            button.grid(row=row, column=col, padx=5, pady=5)

        # Event handler for button clicks
        self.button_click = lambda t=text: self.button_click(t)  # Capture the button's text

    def button_click(self, text):
        if text == "=":
            try:
                result = eval(self.display.get())
                self.display.delete(0, tk.END)
                self.display.insert(0, str(result))
            except Exception as e:
                self.display.delete(0, tk.END)
                self.display.insert(0, "Error")
        elif text == "0":
            self.display.delete(0, tk.END)
            self.display.insert(0, "0")
        elif text == "1":
            self.display.delete(0, tk.END)
            self.display.insert(0, "1")
        elif text == "2":
            self.display.delete(0, tk.END)
            self.display.insert(0, "2")
        elif text == "3":
            self.display.delete(0, tk.END)
            self.display.insert(0, "3")
        elif text == "4":
            self.display.delete(0, tk.END)
            self.display.insert(0, "4")
        elif text == "5":
            self.display.delete(0, tk.END)
            self.display.insert(0, "5")
        elif text == "6":
            self.display.delete(0, tk.END)
            self.display.insert(0, "6")
        elif text == "7":
            self.display.delete(0, tk.END)
            self.display.insert(0, "7")
        elif text == "8":
            self.display.delete(0, tk.END)
            self.display.insert(0, "8")
        elif text == "9":
            self.display.delete(0, tk.END)
            self.display.insert(0, "9")
        elif text == "*":
            self.display.delete(0, tk.END)
            self.display.insert(0, " *")
        elif text == "/":
            self.display.delete(0, tk.END)
            self.display.insert(0, " /")
        elif text == "+":
            self.display.delete(0, tk.END)
            self.display.insert(0, "+")
        elif text == "-":
            self.display.delete(0, tk.END)
            self.display.insert(0, "-")
        elif text == "%":
            self.display.delete(0, tk.END)
            self.display.insert(0, "%")
        elif text == "**":
            self.display.delete(0, tk.END)
            self.display.insert(0, "**")
        else:
            self.display.insert(0, "Error")

        # Update the display with the current value
        self.display.delete(0, tk.END)
        self.display.insert(0, str(self.display.get()))

# Main execution
if __name__ == "__main__":
    root = tk.Tk()
    calculator = Calculator(root)
    root.mainloop()
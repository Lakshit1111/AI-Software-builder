# Import necessary libraries
import tkinter as tk

class Calculator:
    def __init__(self):
        self.window = tk.Tk()
        self.window.title("Simple Calculator")
        self.entry_field = tk.Entry(self.window, width=35, borderwidth=5)
        self.entry_field.grid(row=0, column=0, columnspan=4)

        # Create buttons for digits 0-9
        button_1 = tk.Button(self.window, text="1", padx=40, pady=20, command=lambda: self.append_to_entry("1"))
        button_2 = tk.Button(self.window, text="2", padx=40, pady=20, command=lambda: self.append_to_entry("2"))
        button_3 = tk.Button(self.window, text="3", padx=40, pady=20, command=lambda: self.append_to_entry("3"))
        button_4 = tk.Button(self.window, text="4", padx=40, pady=20, command=lambda: self.append_to_entry("4"))
        button_5 = tk.Button(self.window, text="5", padx=40, pady=20, command=lambda: self.append_to_entry("5"))
        button_6 = tk.Button(self.window, text="6", padx=40, pady=20, command=lambda: self.append_to_entry("6"))
        button_7 = tk.Button(self.window, text="7", padx=40, pady=20, command=lambda: self.append_to_entry("7"))
        button_8 = tk.Button(self.window, text="8", padx=40, pady=20, command=lambda: self.append_to_entry("8"))
        button_9 = tk.Button(self.window, text="9", padx=40, pady=20, command=lambda: self.append_to_entry("9"))
        button_0 = tk.Button(self.window, text="0", padx=40, pady=20, command=lambda: self.append_to_entry("0"))

        # Create buttons for operators
        button_add = tk.Button(self.window, text="+", padx=39, pady=20, command=lambda: self.append_to_entry("+"))
        button_subtract = tk.Button(self.window, text="-", padx=40, pady=20, command=lambda: self.append_to_entry("-"))
        button_multiply = tk.Button(self.window, text="*", padx=40, pady=20, command=lambda: self.append_to_entry("*"))
        button_divide = tk.Button(self.window, text="/", padx=41, pady=20, command=lambda: self.append_to_entry("/"))

        # Place buttons in the window
        button_1.grid(row=3, column=0)
        button_2.grid(row=3, column=1)
        button_3.grid(row=3, column=2)

        button_4.grid(row=2, column=0)
        button_5.grid(row=2, column=1)
        button_6.grid(row=2, column=2)

        button_7.grid(row=1, column=0)
        button_8.grid(row=1, column=1)
        button_9.grid(row=1, column=2)

        button_0.grid(row=4, column=0)
        button_add.grid(row=1, column=3)
        button_subtract.grid(row=2, column=3)
        button_multiply.grid(row=3, column=3)
        button_divide.grid(row=4, column=3)

    def append_to_entry(self, value):
        current_value = self.entry_field.get()
        if current_value != "":
            self.entry_field.delete(0, tk.END)
        self.entry_field.insert(tk.END, value)

    def run(self):
        self.window.mainloop()

if __name__ == "__main__":
    calculator = Calculator()
    calculator.run()
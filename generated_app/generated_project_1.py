import tkinter as tk

class Calculator:
    def __init__(self):
        self.window = tk.Tk()
        self.window.title("Calculator")
        self.entry_field = tk.Entry(self.window, width=35, borderwidth=5)
        self.entry_field.grid(row=0, column=0, columnspan=4)

        buttons = [
            '7', '8', '9',
            '4', '5', '6',
            '1', '2', '3',
            '0', '=', 'C'
        ]

        row_val = 1
        col_val = 0

        for button in buttons:
            if button == '=':
                tk.Button(self.window, text=button, width=10, command=lambda button=button: self.calculate()).grid(row=row_val, column=col_val)
            else:
                tk.Button(self.window, text=button, width=10, command=lambda button=button: self.click_button(button)).grid(row=row_val, column=col_val)

            col_val += 1
            if col_val > 2:
                col_val = 0
                row_val += 1

        self.window.mainloop()

    def click_button(self, button):
        if button == 'C':
            self.entry_field.delete(0, tk.END)
        else:
            self.entry_field.insert(tk.END, str(button))

    def calculate(self):
        try:
            result = eval(self.entry_field.get())
            self.entry_field.delete(0, tk.END)
            self.entry_field.insert(tk.END, str(result))
        except Exception as e:
            self.entry_field.delete(0, tk.END)
            self.entry_field.insert(tk.END, "Error")

Calculator()
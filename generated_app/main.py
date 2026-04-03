from tkinter import *

class CalculatorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Simple Calculator")

        self.result_var = Variable()
        self.result_label = Label(root, textvariable=self.result_var)
        self.result_label.pack()

        self.create_ui()

    def create_ui(self):
        # Input Fields
        self.number1_entry = Entry(self.root, width=10)
        self.number1_entry.pack(pady=5)

        self.number2_entry = Entry(self.root, width=10)
        self.number2_entry.pack(pady=5)

        # Operation Selection
        self.operation_var = StringVar()
        self.operation_var.set("Addition")
        self.operation_dropdown = OptionMenu(self.root, self.operation_var, "Addition", "Subtraction", "Multiplication", "Division")
        self.operation_dropdown.pack(pady=5)

        # Calculate Button
        self.calculate_button = Button(self.root, text="Calculate", command=self.perform_calculation)
        self.calculate_button.pack(pady=10)

    def perform_calculation(self):
        try:
            num1 = float(self.number1_entry.get())
            num2 = float(self.number2_entry.get())

            if self.operation_var.get() == "Division" and num2 == 0:
                self.result_var.set("Error: Division by zero")
                return

            operation = self.operation_var.get()

            if operation == "Addition":
                result = num1 + num2
            elif operation == "Subtraction":
                result = num1 - num2
            elif operation == "Multiplication":
                result = num1 * num2
            elif operation == "Division":
                result = num1 / num2

            self.result_var.set(result)

        except ValueError:
            self.result_var.set("Error: Please enter valid numbers")

if __name__ == "__main__":
    root = Tk()
    app = CalculatorApp(root)
    root.mainloop()
import tkinter as tk
from tkinter import ttk
from PIL import ImageGrab, ImageTk, ImageChops


def similar(left, right):
    if right is None or left.size != right.size:
        return False
    histogram = ImageChops.difference(left, right).histogram()
    return sum(histogram[20:]) < max(4, left.width * left.height * 0.0006)


class ScreenWatch:
    def __init__(self, parent, busy, submit):
        self.root = parent.winfo_toplevel()
        self.busy = busy
        self.submit = submit
        self.region = None
        self.timer = None
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=4)
        self.button = ttk.Button(row, text="Auto-read screen", command=self.toggle)
        self.button.pack(side="left")
        self.message = tk.StringVar(value="Screen watching off")
        ttk.Label(row, textvariable=self.message).pack(side="left", padx=8)

    def toggle(self):
        if self.region:
            self.stop()
            return
        self.button.state(["disabled"])
        self.root.withdraw()
        self.root.after(350, self.choose)

    def stop(self):
        if self.timer is not None:
            self.root.after_cancel(self.timer)
            self.timer = None
        self.region = None
        self.button.configure(text="Auto-read screen")
        self.message.set("Screen watching off")

    def choose(self):
        try:
            desktop = ImageGrab.grab()
        except Exception as exc:
            self.root.deiconify()
            self.button.state(["!disabled"])
            self.message.set(str(exc))
            return
        original = desktop.size
        desktop.thumbnail((int(self.root.winfo_screenwidth() * .86),
                           int(self.root.winfo_screenheight() * .76)))
        window = tk.Toplevel(self.root)
        window.title("Drag over the question area • Esc to cancel")
        canvas = tk.Canvas(window, width=desktop.width, height=desktop.height,
                           highlightthickness=0, cursor="crosshair")
        canvas.pack()
        canvas.preview = ImageTk.PhotoImage(desktop)
        canvas.create_image(0, 0, image=canvas.preview, anchor="nw")
        box = canvas.create_rectangle(0, 0, 0, 0, outline="#ff7900", width=3)
        origin = []

        def finish(region=None):
            window.destroy()
            self.root.deiconify()
            self.button.state(["!disabled"])
            if region:
                self.region = region
                self.previous = self.sent = None
                self.button.configure(text="Stop auto-read")
                self.message.set("Watching selected screen area")
                self.timer = self.root.after(850, self.check)

        def press(event):
            origin[:] = [event.x, event.y]

        def release(event):
            if not origin:
                return
            x1, x2 = sorted((origin[0], min(max(0, event.x), desktop.width)))
            y1, y2 = sorted((origin[1], min(max(0, event.y), desktop.height)))
            if x2 - x1 >= 12 and y2 - y1 >= 8:
                finish(tuple(round(value * original[i % 2] / desktop.size[i % 2])
                             for i, value in enumerate((x1, y1, x2, y2))))

        canvas.bind("<Button-1>", press)
        canvas.bind("<B1-Motion>", lambda e: canvas.coords(box, *origin, e.x, e.y) if origin else None)
        canvas.bind("<ButtonRelease-1>", release)
        window.bind("<Escape>", lambda e: finish())
        window.protocol("WM_DELETE_WINDOW", finish)
        window.focus_force()

    def check(self):
        self.timer = None
        try:
            if not self.busy():
                image = ImageGrab.grab(bbox=self.region)
                signature = image.convert("L")
                signature.thumbnail((640, 400))
                if similar(signature, self.previous) and not similar(signature, self.sent):
                    self.submit(image)
                    self.sent = signature
                self.previous = signature
        except Exception as exc:
            self.stop()
            self.message.set(f"Auto-read stopped: {exc}")
            return
        self.timer = self.root.after(650, self.check)

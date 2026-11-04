
import customtkinter as ctk
import psutil

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class WinToolKit(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("WinToolKit v0.2")
        self.geometry("850x550")
        self.minsize(650, 450)

        self.heading = ctk.CTkLabel(
            self,
            text="WinToolKit",
            font=("Segoe UI", 30, "bold")
        )
        self.heading.pack(pady=(25, 5))

        self.subtitle = ctk.CTkLabel(
            self,
            text="Windows Maintenance & Gaming Utilities",
            text_color="gray"
        )
        self.subtitle.pack(pady=(0, 25))

        self.cpu_label = ctk.CTkLabel(self, text="CPU: Loading...")
        self.cpu_label.pack(pady=10)

        self.ram_label = ctk.CTkLabel(self, text="RAM: Loading...")
        self.ram_label.pack(pady=10)

        self.disk_label = ctk.CTkLabel(self, text="Disk: Loading...")
        self.disk_label.pack(pady=10)

        self.refresh_stats()

    def refresh_stats(self):
        cpu = psutil.cpu_percent(interval=None)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage("C:\\")

        self.cpu_label.configure(text=f"CPU Usage: {cpu:.1f}%")
        self.ram_label.configure(text=f"RAM Usage: {ram.percent:.1f}%")
        self.disk_label.configure(text=f"C: Drive Usage: {disk.percent:.1f}%")

        self.after(1000, self.refresh_stats)


if __name__ == "__main__":
    app = WinToolKit()
    app.mainloop()

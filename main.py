
import customtkinter as ctk
import psutil
import platform

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class WinToolKit(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("WinToolKit v0.3")
        self.geometry("1000x650")
        self.minsize(800, 500)

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Navigation sidebar
        self.sidebar = ctk.CTkFrame(
            self, width=200, corner_radius=0
        )
        self.sidebar.grid(
            row=0, column=0, sticky="nsew"
        )
        self.sidebar.grid_propagate(False)

        ctk.CTkLabel(
            self.sidebar,
            text="WinToolKit",
            font=("Segoe UI", 24, "bold")
        ).pack(pady=(30, 35))

        pages = [
            "Dashboard",
            "Maintenance",
            "Gaming",
            "Network",
            "Settings"
        ]

        for page in pages:
            ctk.CTkButton(
                self.sidebar,
                text=page,
                height=40,
                command=lambda p=page: self.show_page(p)
            ).pack(padx=15, pady=6, fill="x")

        # Main content area
        self.content = ctk.CTkFrame(self)
        self.content.grid(
            row=0, column=1, padx=15, pady=15,
            sticky="nsew"
        )

        self.current_page = None
        self.show_page("Dashboard")

    def show_page(self, page):
        # Remove previous page widgets
        for widget in self.content.winfo_children():
            widget.destroy()

        self.current_page = page

        ctk.CTkLabel(
            self.content,
            text=page,
            font=("Segoe UI", 28, "bold")
        ).pack(pady=(25, 20))

        if page == "Dashboard":
            self.build_dashboard()
        else:
            ctk.CTkLabel(
                self.content,
                text=f"{page} features coming soon!",
                font=("Segoe UI", 16)
            ).pack(pady=30)

    def build_dashboard(self):
        self.cpu_label = ctk.CTkLabel(
            self.content, text="CPU Usage: Loading..."
        )
        self.cpu_label.pack(pady=10)

        self.cpu_bar = ctk.CTkProgressBar(self.content)
        self.cpu_bar.pack(fill="x", padx=40)

        self.ram_label = ctk.CTkLabel(
            self.content, text="RAM Usage: Loading..."
        )
        self.ram_label.pack(pady=(25, 10))

        self.ram_bar = ctk.CTkProgressBar(self.content)
        self.ram_bar.pack(fill="x", padx=40)

        self.disk_label = ctk.CTkLabel(
            self.content, text="Disk Usage: Loading..."
        )
        self.disk_label.pack(pady=(25, 10))

        self.disk_bar = ctk.CTkProgressBar(self.content)
        self.disk_bar.pack(fill="x", padx=40)

        ctk.CTkLabel(
            self.content,
            text=f"Operating System: {platform.system()} "
                 f"{platform.release()}"
        ).pack(pady=30)

        self.refresh_stats()

    def refresh_stats(self):
        # Stop updates when dashboard is not active
        if self.current_page != "Dashboard":
            return

        cpu = psutil.cpu_percent(interval=None)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage("C:\\")

        self.cpu_label.configure(
            text=f"CPU Usage: {cpu:.1f}%"
        )
        self.cpu_bar.set(cpu / 100)

        self.ram_label.configure(
            text=f"RAM Usage: {ram.percent:.1f}%"
        )
        self.ram_bar.set(ram.percent / 100)

        self.disk_label.configure(
            text=f"C: Drive Usage: {disk.percent:.1f}%"
        )
        self.disk_bar.set(disk.percent / 100)

        # Refresh once per second
        self.after(1000, self.refresh_stats)


if __name__ == "__main__":
    app = WinToolKit()
    app.mainloop()

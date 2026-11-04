"""WinToolKit v0.4: system monitoring and Windows maintenance."""
import platform
import queue
import subprocess
import threading
from tkinter import messagebox

import customtkinter as ctk
import psutil

from modules.network import flush_dns
from modules.system import REPAIR_COMMANDS, is_admin, relaunch_as_admin

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class WinToolKit(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("WinToolKit v0.4")
        self.geometry("1050x690")
        self.minsize(850, 550)
        self.current_page = None
        self.events = queue.Queue()
        self.running_task = None
        self.maintenance_log = ["Ready to run maintenance tasks."]
        self.admin = is_admin()

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.sidebar = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)
        ctk.CTkLabel(self.sidebar, text="WinToolKit", font=("Segoe UI", 24, "bold")).pack(pady=(30, 20))
        self.privilege_label = ctk.CTkLabel(
            self.sidebar, text="Administrator" if self.admin else "Standard user",
            text_color="#70c080" if self.admin else "#e0b66a"
        )
        self.privilege_label.pack(pady=(0, 20))
        for page in ("Dashboard", "Maintenance", "Gaming", "Network", "Settings"):
            ctk.CTkButton(self.sidebar, text=page, height=40,
                          command=lambda p=page: self.show_page(p)).pack(padx=15, pady=6, fill="x")
        self.content = ctk.CTkFrame(self)
        self.content.grid(row=0, column=1, padx=15, pady=15, sticky="nsew")
        self.show_page("Dashboard")
        self.after(1000, self.refresh_stats)
        self.after(100, self.process_events)

    def show_page(self, page):
        for widget in self.content.winfo_children():
            widget.destroy()
        self.current_page = page
        ctk.CTkLabel(self.content, text=page, font=("Segoe UI", 28, "bold")).pack(pady=(20, 15))
        if page == "Dashboard":
            self.build_dashboard()
            self.update_dashboard()
        elif page == "Maintenance":
            self.build_maintenance()
        else:
            ctk.CTkLabel(self.content, text=f"{page} features coming soon!",
                         font=("Segoe UI", 16)).pack(pady=30)

    def build_dashboard(self):
        self.cpu_label = ctk.CTkLabel(self.content, text="CPU: Loading...")
        self.cpu_label.pack(pady=8)
        self.cpu_bar = ctk.CTkProgressBar(self.content)
        self.cpu_bar.pack(fill="x", padx=40)
        self.ram_label = ctk.CTkLabel(self.content, text="RAM: Loading...")
        self.ram_label.pack(pady=(24, 8))
        self.ram_bar = ctk.CTkProgressBar(self.content)
        self.ram_bar.pack(fill="x", padx=40)
        self.disk_label = ctk.CTkLabel(self.content, text="Disk: Loading...")
        self.disk_label.pack(pady=(24, 8))
        self.disk_bar = ctk.CTkProgressBar(self.content)
        self.disk_bar.pack(fill="x", padx=40)
        ctk.CTkLabel(self.content, text=f"Operating System: {platform.system()} {platform.release()}").pack(pady=30)

    def update_dashboard(self):
        if self.current_page != "Dashboard":
            return
        cpu = psutil.cpu_percent(interval=None)
        ram = psutil.virtual_memory().percent
        disk = psutil.disk_usage("C:\\").percent
        for label, bar, name, value in (
            (self.cpu_label, self.cpu_bar, "CPU Usage", cpu),
            (self.ram_label, self.ram_bar, "RAM Usage", ram),
            (self.disk_label, self.disk_bar, "C: Drive Usage", disk),
        ):
            label.configure(text=f"{name}: {value:.1f}%")
            bar.set(value / 100)

    def refresh_stats(self):
        if self.current_page == "Dashboard":
            self.update_dashboard()
        self.after(1000, self.refresh_stats)

    def build_maintenance(self):
        if not self.admin:
            ctk.CTkLabel(self.content, text="System repairs require administrator permissions.",
                         text_color="#e0b66a").pack(pady=(0, 6))
            ctk.CTkButton(self.content, text="Restart as Administrator",
                          command=self.request_elevation).pack(pady=(0, 12))
        else:
            ctk.CTkLabel(self.content, text="Running as Administrator",
                         text_color="#70c080").pack(pady=(0, 12))

        ctk.CTkLabel(self.content, text="Maintenance Utilities",
                     font=("Segoe UI", 19, "bold")).pack(pady=(0, 10))
        self.task_buttons = {}
        for task in ("Flush DNS Cache", "DISM RestoreHealth", "SFC Scan"):
            button = ctk.CTkButton(self.content, text=task, height=35,
                                   command=lambda t=task: self.start_task(t))
            button.pack(pady=5)
            self.task_buttons[task] = button
        self.update_task_buttons()
        self.maintenance_output = ctk.CTkTextbox(self.content, height=230)
        self.maintenance_output.pack(fill="both", expand=True, padx=25, pady=(15, 20))
        self.maintenance_output.insert("end", "\n".join(self.maintenance_log) + "\n")
        self.maintenance_output.configure(state="disabled")
        self.maintenance_output.see("end")

    def update_task_buttons(self):
        if self.current_page == "Maintenance":
            for button in self.task_buttons.values():
                button.configure(state="disabled" if self.running_task else "normal")

    def append_log(self, line):
        self.maintenance_log.append(line)
        if self.current_page == "Maintenance":
            self.maintenance_output.configure(state="normal")
            self.maintenance_output.insert("end", line + "\n")
            self.maintenance_output.see("end")
            self.maintenance_output.configure(state="disabled")

    def request_elevation(self):
        if self.running_task:
            messagebox.showwarning("Task running", "Wait for the active task to finish first.")
            return
        if not messagebox.askyesno("Administrator permissions",
                                   "Restart WinToolKit as administrator? Windows will ask for permission."):
            return
        try:
            relaunch_as_admin()
        except OSError as exc:
            messagebox.showerror("Elevation failed", str(exc))
            return
        self.destroy()

    def start_task(self, task):
        if self.running_task:
            return
        if not self.admin:
            messagebox.showwarning("Administrator required",
                                   "Restart WinToolKit as administrator to run this task.")
            return
        description = {
            "Flush DNS Cache": "Clear the Windows DNS resolver cache?",
            "DISM RestoreHealth": "Repair the Windows component store using DISM? This may take a while.",
            "SFC Scan": "Scan and repair protected Windows system files? This may take a while.",
        }[task]
        if not messagebox.askyesno("Confirm maintenance", description):
            return
        self.running_task = task
        self.update_task_buttons()
        self.append_log(f"\n--- Starting: {task} ---")
        threading.Thread(target=self.task_worker, args=(task,), daemon=True).start()

    def task_worker(self, task):
        try:
            if task == "Flush DNS Cache":
                self.events.put(("line", flush_dns()))
                code = 0
            else:
                command = REPAIR_COMMANDS[task]
                with subprocess.Popen(
                    command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, errors="replace", bufsize=1,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                ) as proc:
                    for line in proc.stdout:
                        if line.strip():
                            self.events.put(("line", line.rstrip()))
                    code = proc.wait()
            self.events.put(("done", task, code))
        except Exception as exc:
            self.events.put(("error", task, str(exc)))

    def process_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "line":
                    self.append_log(event[1])
                elif event[0] == "done":
                    _, task, code = event
                    self.append_log(f"--- {task}: {'completed (exit code 0)' if code == 0 else f'failed (exit code {code})'} ---")
                    self.running_task = None
                    self.update_task_buttons()
                elif event[0] == "error":
                    _, task, error = event
                    self.append_log(f"ERROR ({task}): {error}")
                    self.running_task = None
                    self.update_task_buttons()
        except queue.Empty:
            pass
        self.after(100, self.process_events)


if __name__ == "__main__":
    WinToolKit().mainloop()

"""WinToolKit v0.7: Windows dashboard, maintenance and gaming tools."""
import os
import platform
import queue
import subprocess
import threading
from tkinter import messagebox

import customtkinter as ctk
import psutil

from modules.activity import LOG_PATH, read_recent, record
from modules.gaming import gpu_info, game_processes, power_plans, activate_power_plan, tcp_latency
from modules.cleanup import locations, scan, clean
from modules.network import flush_dns
from modules.system import REPAIR_COMMANDS, is_admin, relaunch_as_admin

VERSION = '0.7.0'
ctk.set_appearance_mode('dark')
ctk.set_default_color_theme('blue')


class WinToolKit(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f'WinToolKit v{VERSION}')
        self.geometry('1120x760')
        self.minsize(900, 600)
        self.admin = is_admin()
        self.events = queue.Queue()
        self.running_task = None
        self.current_page = 'Dashboard'
        self.current_tab = 'System Repair'
        self.cleanup_selection = {}
        self.cleanup_scan = None
        self.maintenance_log = ['Ready to run maintenance tasks.']
        self.task_buttons = []
        self.gaming_busy = False
        self.gaming_plans = {}
        self.last_gaming_refresh = 0
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(self, width=205, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky='nsew')
        self.sidebar.grid_propagate(False)
        ctk.CTkLabel(self.sidebar, text='WinToolKit', font=('Segoe UI', 25, 'bold')).pack(pady=(28, 4))
        ctk.CTkLabel(self.sidebar, text=f'v{VERSION}  •  ' + ('Administrator' if self.admin else 'Standard user'),
                     text_color='#70c080' if self.admin else '#e0b66a').pack(pady=(0, 28))
        for name in ('Dashboard', 'Maintenance', 'Gaming', 'Network', 'Settings', 'Activity'):
            ctk.CTkButton(self.sidebar, text=name, height=39,
                          command=lambda n=name: self.show_page(n)).pack(fill='x', padx=16, pady=5)

        self.content = ctk.CTkFrame(self)
        self.content.grid(row=0, column=1, padx=15, pady=15, sticky='nsew')
        self.show_page('Dashboard')
        self.after(1000, self.refresh_stats)
        self.after(100, self.process_events)

    def show_page(self, page):
        self.current_page = page
        for widget in self.content.winfo_children():
            widget.destroy()
        self.task_buttons = []
        ctk.CTkLabel(self.content, text=page, font=('Segoe UI', 28, 'bold')).pack(pady=(18, 12))
        if page == 'Dashboard':
            self.build_dashboard()
            self.update_dashboard()
        elif page == 'Maintenance':
            self.build_maintenance()
        elif page == 'Gaming':
            self.build_gaming()
        elif page == 'Activity':
            self.build_activity()
        elif page == 'Settings':
            ctk.CTkLabel(self.content, text=f'WinToolKit version {VERSION}').pack(pady=12)
            ctk.CTkLabel(self.content, text=f'Activity log: {LOG_PATH}', wraplength=650).pack(pady=12)
        else:
            ctk.CTkLabel(self.content, text=f'{page} tools coming in a future release.').pack(pady=25)

    def build_gaming(self):
        """Gaming diagnostics. All slow system calls run off the UI thread."""
        ctk.CTkLabel(self.content, text='Gaming & Performance',
                     font=('Segoe UI', 18, 'bold')).pack(pady=(0, 10))
        self.gaming_status = ctk.CTkLabel(self.content, text='Ready to check gaming performance.')
        self.gaming_status.pack(pady=5)
        self.gpu_label = ctk.CTkLabel(self.content, text='GPU: Checking...', wraplength=680)
        self.gpu_label.pack(pady=4)
        self.gpu_usage_label = ctk.CTkLabel(self.content, text='GPU load: Checking...')
        self.gpu_usage_label.pack(pady=2)
        self.vram_label = ctk.CTkLabel(self.content, text='VRAM: Checking...')
        self.vram_label.pack(pady=2)
        self.games_label = ctk.CTkLabel(self.content, text='Known running games: Checking...', wraplength=680)
        self.games_label.pack(pady=8)
        self.latency_label = ctk.CTkLabel(self.content, text='TCP latency: Not tested')
        self.latency_label.pack(pady=5)
        ctk.CTkButton(self.content, text='Test Network Latency (1.1.1.1:443)',
                      command=self.start_latency_test).pack(pady=5)
        ctk.CTkButton(self.content, text='Refresh GPU and Game Processes',
                      command=self.start_gaming_refresh).pack(pady=5)
        ctk.CTkLabel(self.content, text='Windows Power Plan',
                     font=('Segoe UI', 17, 'bold')).pack(pady=(14, 6))
        self.power_plan_menu = ctk.CTkOptionMenu(self.content, values=['Loading...'])
        self.power_plan_menu.pack(pady=4)
        ctk.CTkButton(self.content, text='Apply Selected Power Plan',
                      command=self.request_power_plan).pack(pady=5)
        ctk.CTkButton(self.content, text='Refresh Power Plans',
                      command=self.start_power_plan_refresh).pack(pady=4)
        ctk.CTkLabel(self.content,
                     text='GPU load and VRAM monitoring currently support NVIDIA via nvidia-smi. '
                          'Other adapters show their name, but live metrics may be unavailable. '
                          'Network test measures TCP connection time, not game ping.',
                     wraplength=680, text_color='gray70').pack(padx=25, pady=14)
        self.start_gaming_refresh()
        self.start_power_plan_refresh()

    def start_gaming_refresh(self):
        if self.gaming_busy:
            return
        self.gaming_busy = True
        if self.current_page == 'Gaming':
            self.gaming_status.configure(text='Refreshing GPU and running games...')
        threading.Thread(target=self.gaming_worker, daemon=True).start()

    def gaming_worker(self):
        try:
            self.events.put(('gaming_data', gpu_info(), game_processes()))
        except Exception as exc:
            self.events.put(('gaming_error', str(exc)))

    def start_latency_test(self):
        if self.current_page == 'Gaming':
            self.latency_label.configure(text='TCP latency: Testing...')
        threading.Thread(target=self.latency_worker, daemon=True).start()

    def latency_worker(self):
        try:
            self.events.put(('latency', f'{tcp_latency()} ms (TCP connection)'))
        except OSError as exc:
            self.events.put(('latency', f'Unavailable: {exc}'))

    def start_power_plan_refresh(self):
        threading.Thread(target=self.power_plan_worker, daemon=True).start()

    def power_plan_worker(self):
        try:
            self.events.put(('power_plans', power_plans()))
        except Exception as exc:
            self.events.put(('gaming_error', f'Power plans: {exc}'))

    def request_power_plan(self):
        if self.running_task:
            messagebox.showwarning('Task running', 'Wait for the maintenance task to finish.')
            return
        choice = self.power_plan_menu.get()
        guid = self.gaming_plans.get(choice)
        if not guid:
            messagebox.showinfo('No plan selected', 'Refresh and select an available power plan.')
            return
        if not messagebox.askyesno('Change Windows power plan',
                                   f'Activate {choice}? This changes your Windows power settings.'):
            return
        self.running_task = 'Change power plan'
        self.append_log(f'--- Activating power plan: {choice} ---')
        threading.Thread(target=self.power_plan_worker_apply, args=(guid,), daemon=True).start()

    def power_plan_worker_apply(self, guid):
        try:
            activate_power_plan(guid)
            self.events.put(('power_applied',))
        except Exception as exc:
            self.events.put(('error', 'Change power plan', str(exc)))

    def build_dashboard(self):
        ctk.CTkLabel(self.content, text='Live System Overview', font=('Segoe UI', 18, 'bold')).pack(pady=(0, 12))
        cards = ctk.CTkFrame(self.content, fg_color='transparent')
        cards.pack(fill='x', padx=25)
        self.stats = {}
        for title in ('CPU', 'RAM', 'C: Drive'):
            card = ctk.CTkFrame(cards)
            card.pack(side='left', expand=True, fill='both', padx=6)
            ctk.CTkLabel(card, text=title, font=('Segoe UI', 16, 'bold')).pack(pady=(18, 5))
            label = ctk.CTkLabel(card, text='Loading...', font=('Segoe UI', 22))
            label.pack(pady=5)
            bar = ctk.CTkProgressBar(card)
            bar.pack(fill='x', padx=16, pady=(8, 20))
            self.stats[title] = (label, bar)
        info = ctk.CTkFrame(self.content)
        info.pack(fill='x', padx=30, pady=25)
        details = [
            ('Operating system', f'{platform.system()} {platform.release()}'),
            ('Processor', platform.processor() or 'Unknown'),
            ('CPU cores', f'{psutil.cpu_count(logical=False) or "?"} physical / {psutil.cpu_count() or "?"} logical'),
            ('Total memory', f'{psutil.virtual_memory().total / (1024**3):.1f} GiB'),
            ('Computer', platform.node()),
        ]
        for title, value in details:
            row = ctk.CTkFrame(info, fg_color='transparent')
            row.pack(fill='x', padx=18, pady=5)
            ctk.CTkLabel(row, text=title + ':', width=160, anchor='w').pack(side='left')
            ctk.CTkLabel(row, text=value, anchor='w', wraplength=490).pack(side='left', fill='x', expand=True)

    def update_dashboard(self):
        if self.current_page != 'Dashboard':
            return
        values = {'CPU': psutil.cpu_percent(interval=None),
                  'RAM': psutil.virtual_memory().percent,
                  'C: Drive': psutil.disk_usage('C:\\').percent}
        for name, value in values.items():
            label, bar = self.stats[name]
            label.configure(text=f'{value:.1f}%')
            bar.set(value / 100)

    def refresh_stats(self):
        if self.current_page == 'Dashboard':
            self.update_dashboard()
        self.after(1000, self.refresh_stats)

    def build_maintenance(self):
        if self.admin:
            ctk.CTkLabel(self.content, text='Running as Administrator', text_color='#70c080').pack(pady=(0, 10))
        else:
            ctk.CTkButton(self.content, text='Restart as Administrator',
                          command=self.request_elevation).pack(pady=(0, 10))
        tabs = ctk.CTkSegmentedButton(self.content,
                                     values=['System Repair', 'Smart Cleanup', 'Network'],
                                     command=self.show_maintenance_tab)
        tabs.pack(padx=15, pady=(0, 10))
        self.tab_content = ctk.CTkFrame(self.content, fg_color='transparent')
        self.tab_content.pack(fill='x', padx=15, pady=5)
        self.maintenance_output = ctk.CTkTextbox(self.content, height=220)
        self.maintenance_output.pack(fill='both', expand=True, padx=20, pady=(8, 20))
        self.maintenance_output.insert('end', '\n'.join(self.maintenance_log) + '\n')
        self.maintenance_output.configure(state='disabled')
        self.maintenance_output.see('end')
        tabs.set(self.current_tab)
        self.show_maintenance_tab(self.current_tab)

    def show_maintenance_tab(self, tab):
        self.current_tab = tab
        for widget in self.tab_content.winfo_children():
            widget.destroy()
        self.task_buttons = []
        if tab == 'System Repair':
            ctk.CTkLabel(self.tab_content, text='Windows Component & File Repair',
                         font=('Segoe UI', 17, 'bold')).pack(pady=10)
            for task in ('DISM RestoreHealth', 'SFC Scan'):
                button = ctk.CTkButton(self.tab_content, text=task, width=200, height=36,
                                       command=lambda t=task: self.start_task(t))
                button.pack(pady=6)
                self.task_buttons.append(button)
        elif tab == 'Network':
            ctk.CTkLabel(self.tab_content, text='DNS Resolver Maintenance',
                         font=('Segoe UI', 17, 'bold')).pack(pady=10)
            button = ctk.CTkButton(self.tab_content, text='Flush DNS Cache', width=200,
                                   command=lambda: self.start_task('Flush DNS Cache'))
            button.pack(pady=10)
            self.task_buttons.append(button)
        else:
            ctk.CTkLabel(self.tab_content, text='Temporary files older than 24 hours',
                         font=('Segoe UI', 17, 'bold')).pack(pady=8)
            self.cleanup_selection = {}
            for name in locations():
                var = ctk.BooleanVar(value=name == 'User temporary files')
                self.cleanup_selection[name] = var
                ctk.CTkCheckBox(self.tab_content, text=name, variable=var).pack(anchor='w', padx=30, pady=3)
            controls = ctk.CTkFrame(self.tab_content, fg_color='transparent')
            controls.pack(pady=12)
            for label, mode in (('Scan', 'scan'), ('Dry Run', 'dry'), ('Clean Selected', 'clean')):
                button = ctk.CTkButton(controls, text=label, width=130,
                                       command=lambda m=mode: self.start_cleanup(m))
                button.pack(side='left', padx=5)
                self.task_buttons.append(button)
        self.update_task_buttons()

    def update_task_buttons(self):
        for button in self.task_buttons:
            button.configure(state='disabled' if self.running_task else 'normal')

    def append_log(self, line):
        self.maintenance_log.append(line)
        if len(self.maintenance_log) > 1500:
            self.maintenance_log = self.maintenance_log[-1500:]
        try:
            record(line)
        except OSError:
            pass  # Logging failure must not interrupt maintenance.
        if self.current_page == 'Maintenance':
            self.maintenance_output.configure(state='normal')
            self.maintenance_output.insert('end', line + '\n')
            self.maintenance_output.see('end')
            self.maintenance_output.configure(state='disabled')

    def build_activity(self):
        ctk.CTkLabel(self.content, text='Saved activity history',
                     font=('Segoe UI', 17, 'bold')).pack(pady=8)
        ctk.CTkButton(self.content, text='Refresh History', command=self.refresh_activity).pack(pady=5)
        self.activity_output = ctk.CTkTextbox(self.content)
        self.activity_output.pack(fill='both', expand=True, padx=20, pady=15)
        self.refresh_activity()

    def refresh_activity(self):
        try:
            content = read_recent()
        except OSError as exc:
            content = f'Unable to read log: {exc}'
        self.activity_output.configure(state='normal')
        self.activity_output.delete('1.0', 'end')
        self.activity_output.insert('end', content)
        self.activity_output.see('end')
        self.activity_output.configure(state='disabled')

    def request_elevation(self):
        if self.running_task:
            messagebox.showwarning('Task running', 'Wait for the current task to finish.')
            return
        if not messagebox.askyesno('Administrator permissions', 'Restart WinToolKit as administrator?'):
            return
        try:
            relaunch_as_admin()
        except OSError as exc:
            messagebox.showerror('Elevation failed', str(exc))
            return
        self.destroy()

    def start_task(self, task):
        if self.running_task:
            return
        if not self.admin:
            messagebox.showwarning('Administrator required', 'Restart as Administrator to run this task.')
            return
        description = {
            'Flush DNS Cache': 'Clear the Windows DNS resolver cache?',
            'DISM RestoreHealth': 'Repair the Windows component store with DISM? This may take a while.',
            'SFC Scan': 'Scan and repair protected Windows system files? This may take a while.',
        }[task]
        if not messagebox.askyesno('Confirm maintenance', description):
            return
        self.running_task = task
        self.update_task_buttons()
        self.append_log(f'\n--- Starting: {task} ---')
        threading.Thread(target=self.task_worker, args=(task,), daemon=True).start()

    def task_worker(self, task):
        try:
            if task == 'Flush DNS Cache':
                self.events.put(('line', flush_dns()))
                code = 0
            else:
                with subprocess.Popen(REPAIR_COMMANDS[task], stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT, text=True, errors='replace',
                                      bufsize=1, creationflags=subprocess.CREATE_NO_WINDOW) as proc:
                    for line in proc.stdout:
                        if line.strip():
                            self.events.put(('line', line.rstrip()))
                    code = proc.wait()
            self.events.put(('done', task, code))
        except Exception as exc:
            self.events.put(('error', task, str(exc)))

    def start_cleanup(self, mode):
        if self.running_task:
            return
        selected = {name for name, var in self.cleanup_selection.items() if var.get()}
        if not selected:
            messagebox.showinfo('Nothing selected', 'Choose at least one temporary folder.')
            return
        if mode == 'clean':
            if not self.cleanup_scan or self.cleanup_scan[0] != selected:
                messagebox.showwarning('Scan first', 'Scan these selections before cleaning.')
                return
            if not messagebox.askyesno('Confirm deletion',
                    'Delete eligible temporary files older than 24 hours? This cannot be undone.'):
                return
        self.running_task = f'Cleanup: {mode}'
        self.update_task_buttons()
        self.append_log(f'\n--- Cleanup {mode}: {", ".join(sorted(selected))} ---')
        threading.Thread(target=self.cleanup_worker, args=(mode, selected), daemon=True).start()

    def cleanup_worker(self, mode, selected):
        try:
            result = scan(selected) if mode == 'scan' else clean(selected, dry_run=mode == 'dry')
            self.events.put(('cleanup_done', mode, selected, result))
        except Exception as exc:
            self.events.put(('error', f'Cleanup: {mode}', str(exc)))

    def process_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == 'line':
                    self.append_log(event[1])
                elif event[0] == 'done':
                    _, task, code = event
                    self.append_log(f'--- {task}: {"completed" if code == 0 else "failed"} (exit code {code}) ---')
                    self.running_task = None
                    self.update_task_buttons()
                elif event[0] == 'cleanup_done':
                    _, mode, selected, result = event
                    self.cleanup_scan = (selected, result) if mode == 'scan' else None
                    for name, values in result.items():
                        count, size = values[:2]
                        skipped = f', skipped: {values[2]}' if len(values) > 2 else ''
                        self.append_log(f'{name}: {count} files, {size / 1048576:.2f} MiB{skipped}')
                    self.append_log('Dry run only; no files deleted.' if mode == 'dry' else
                                    'Scan finished.' if mode == 'scan' else 'Cleanup finished.')
                    self.running_task = None
                    self.update_task_buttons()
                elif event[0] == 'gaming_data':
                    self.gaming_busy = False
                    _, gpu, games = event
                    if self.current_page == 'Gaming':
                        self.gaming_status.configure(text='Gaming diagnostics updated.')
                        self.gpu_label.configure(text=f"GPU: {gpu['name']}")
                        self.gpu_usage_label.configure(text=f"GPU load: {gpu['utilization']}")
                        self.vram_label.configure(text=f"VRAM: {gpu['vram']}")
                        text = '; '.join(f'{name} (PID {pid}, {mib} MiB RAM)' for name, pid, mib in games)
                        self.games_label.configure(text='Known running games: ' + (text or 'None detected'))
                elif event[0] == 'gaming_error':
                    self.gaming_busy = False
                    if self.current_page == 'Gaming':
                        self.gaming_status.configure(text=f'Diagnostics: {event[1]}')
                elif event[0] == 'latency':
                    if self.current_page == 'Gaming':
                        self.latency_label.configure(text=f'TCP latency: {event[1]}')
                elif event[0] == 'power_plans':
                    plans = event[1]
                    self.gaming_plans = {f'{name} [{guid[:8]}]': guid for guid, name, active in plans}
                    if self.current_page == 'Gaming':
                        labels = list(self.gaming_plans) or ['No power plans found']
                        self.power_plan_menu.configure(values=labels)
                        active = next((f'{name} [{guid[:8]}]' for guid, name, is_active in plans if is_active), labels[0])
                        self.power_plan_menu.set(active)
                elif event[0] == 'power_applied':
                    self.append_log('--- Power plan activated successfully ---')
                    self.running_task = None
                    self.update_task_buttons()
                    self.start_power_plan_refresh()
                elif event[0] == 'error':
                    _, task, error = event
                    self.append_log(f'ERROR ({task}): {error}')
                    self.running_task = None
                    self.update_task_buttons()
        except queue.Empty:
            pass
        self.after(100, self.process_events)


if __name__ == '__main__':
    WinToolKit().mainloop()

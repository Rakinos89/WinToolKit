"""RaksToolKit: Windows dashboard, maintenance and gaming tools."""
import os
import platform
import queue
import sys
from pathlib import Path
import subprocess
import threading
from tkinter import TclError, messagebox

import customtkinter as ctk
import psutil

from modules.activity import LOG_PATH, read_recent, record
from modules.privacy import load_privacy, save_privacy, redact
from modules.appearance import ACCENTS, DEFAULT_ACCENT, load_accent, save_accent
from modules.disk_health import disk_health_snapshot
from modules.hardware_history import HardwareHistory
from modules.hardware_graph import HardwareGraph
from modules.hardware_monitor import system_snapshot, volume_snapshot
from modules.hardware_format import format_system, format_volume, format_percent
from modules.gaming import gpu_info, game_processes, power_plans, activate_power_plan, tcp_latency
from modules.cleanup import locations, scan, clean
from modules.network import flush_dns
from modules.network_overview import get_network_overview
from modules.software_updates import check_updates, upgrade_all, upgrade_package, parse_upgrade_table
from modules.system import REPAIR_COMMANDS, is_admin, relaunch_as_admin

VERSION = '1.2.0-dev'
ctk.set_appearance_mode('dark')
ctk.set_default_color_theme('green')


def resource_path(relative_path):
    """Find bundled resources in PyInstaller and local development."""
    base_path = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    return base_path / relative_path


class RaksToolKit(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f'RaksToolKit v{VERSION}')
        icon_path = resource_path(Path('assets') / 'icons' / 'rakstoolkit.ico')
        if icon_path.is_file():
            try:
                self.iconbitmap(str(icon_path))
            except (OSError, TclError):
                pass  # Keep the application usable if Windows rejects the icon.
        self.geometry("1440x1000")
        self.minsize(900, 600)
        self.admin = is_admin()
        self.privacy_mode = load_privacy()
        self.accent_color = load_accent()
        # Set the CTk defaults before creating any controls. This prevents
        # the default green from appearing during initial widget rendering.
        primary, hover = ACCENTS.get(self.accent_color, ACCENTS[DEFAULT_ACCENT])
        ctk.ThemeManager.theme['CTkButton']['fg_color'] = primary
        ctk.ThemeManager.theme['CTkButton']['hover_color'] = hover
        ctk.ThemeManager.theme['CTkCheckBox']['fg_color'] = primary
        ctk.ThemeManager.theme['CTkCheckBox']['hover_color'] = hover
        ctk.ThemeManager.theme['CTkRadioButton']['fg_color'] = primary
        ctk.ThemeManager.theme['CTkRadioButton']['hover_color'] = hover
        ctk.ThemeManager.theme['CTkProgressBar']['progress_color'] = primary
        ctk.ThemeManager.theme['CTkOptionMenu']['fg_color'] = primary
        ctk.ThemeManager.theme['CTkOptionMenu']['button_color'] = primary
        ctk.ThemeManager.theme['CTkOptionMenu']['button_hover_color'] = hover
        ctk.ThemeManager.theme['CTkSwitch']['progress_color'] = primary

        self.events = queue.Queue()
        self.running_task = None
        self.current_page = 'Dashboard'
        self.current_tab = 'System Repair'
        self.cleanup_selection = {}
        self.cleanup_scan = None
        self.maintenance_log = ['Ready to run maintenance tasks.']
        self.maintenance_state = ('Ready for maintenance tasks.', 'gray70')
        self.task_buttons = []
        self.maintenance_tab_buttons = {}
        self.available_updates = None
        self.selected_update_ids = set()
        self.refresh_after_selected = False
        self.gaming_busy = False
        self.gaming_plans = {}
        self.power_plan_status = ('Power plan: Ready.', 'gray70')
        self.power_plan_refresh_busy = False
        self.power_plan_buttons = []
        self.last_gaming_refresh = 0
        self.dashboard_busy = False
        self.hardware_history = HardwareHistory()
        self.storage_busy = False
        self.network_refreshing = False
        self.network_snapshot = None
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(self, width=205, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky='nsew')
        self.sidebar.grid_propagate(False)
        ctk.CTkLabel(self.sidebar, text='RaksToolKit', font=('Segoe UI', 25, 'bold')).pack(pady=(28, 4))
        ctk.CTkLabel(self.sidebar, text=f'v{VERSION}  •  ' + ('Administrator' if self.admin else 'Standard user'),
                     text_color='#70c080' if self.admin else '#e0b66a').pack(pady=(0, 28))
        for name in ('Dashboard', 'Storage', 'Maintenance', 'Gaming', 'Network', 'Settings', 'Activity'):
            ctk.CTkButton(self.sidebar, text=name, height=39,
                          command=lambda n=name: self.show_page(n)).pack(fill='x', padx=16, pady=5)

        self.content = ctk.CTkFrame(self)
        self.content.grid(row=0, column=1, padx=15, pady=15, sticky='nsew')
        self.show_page('Dashboard')
        self.after(1000, self.refresh_stats)
        self.after(2000, self.refresh_gaming_live)
        self.after(100, self.process_events)

    def show_page(self, page):
        self.current_page = page
        self.accent_palette_buttons = {}
        self.maintenance_tab_buttons = {}
        for widget in self.content.winfo_children():
            widget.destroy()
        self.task_buttons = []
        ctk.CTkLabel(self.content, text=page, font=('Segoe UI', 28, 'bold')).pack(pady=(18, 12))
        if page == 'Dashboard':
            self.build_dashboard()
            self.update_dashboard()
        elif page == 'Storage':
            self.build_storage()
        elif page == 'Maintenance':
            self.build_maintenance()
        elif page == 'Gaming':
            self.build_gaming()
        elif page == 'Activity':
            self.build_activity()
        elif page == 'Settings':
            self.build_settings()
        elif page == 'Network':
            self.build_network_overview()
        else:
            ctk.CTkLabel(self.content, text=f'{page} tools coming in a future release.').pack(pady=25)
        self.apply_accent()

    def apply_accent(self):
        """Apply the saved accent to current widgets and persistent navigation."""
        primary, hover = ACCENTS.get(self.accent_color, ACCENTS[DEFAULT_ACCENT])

        def walk(parent):
            for widget in parent.winfo_children():
                # Palette buttons display their own colors, not the active accent.
                if (widget in getattr(self, 'accent_palette_buttons', {}).values()
                        or widget in getattr(self, 'maintenance_tab_buttons', {}).values()):
                    continue
                try:
                    if isinstance(widget, HardwareGraph):
                        widget.set_theme(primary)
                    elif isinstance(widget, ctk.CTkSegmentedButton):
                        widget.configure(selected_color=primary, selected_hover_color=hover,
                                         unselected_color='#454545', unselected_hover_color='#555555')
                    elif isinstance(widget, ctk.CTkButton):
                        widget.configure(fg_color=primary, hover_color=hover)
                    elif isinstance(widget, ctk.CTkSwitch):
                        widget.configure(fg_color='#555555', progress_color=primary,
                                         button_color='#E5E5E5', button_hover_color='#FFFFFF')
                    elif isinstance(widget, (ctk.CTkCheckBox, ctk.CTkRadioButton)):
                        widget.configure(fg_color=primary, hover_color=hover)
                    elif isinstance(widget, ctk.CTkProgressBar):
                        widget.configure(progress_color=primary)
                    elif isinstance(widget, ctk.CTkOptionMenu):
                        widget.configure(fg_color=primary, button_color=primary,
                                         button_hover_color=hover)
                except (TclError, ValueError):
                    pass  # A widget may be in the process of being destroyed.
                walk(widget)

        walk(self.sidebar)
        walk(self.content)
        self.update_maintenance_tab_colors()
        for name, button in getattr(self, 'accent_palette_buttons', {}).items():
            button.configure(text=('✓ ' if name == self.accent_color else '') + name)

    def change_accent(self, name):
        """Save and immediately apply a selected accent color."""
        if name not in ACCENTS:
            return
        previous = self.accent_color
        try:
            save_accent(name)
        except OSError as exc:
            messagebox.showerror('Could not save setting', str(exc))
            self.accent_color = previous
            return
        self.accent_color = name
        primary, hover = ACCENTS.get(name, ACCENTS[DEFAULT_ACCENT])
        for widget_type in ('CTkButton', 'CTkCheckBox', 'CTkRadioButton'):
            ctk.ThemeManager.theme[widget_type]['fg_color'] = primary
            ctk.ThemeManager.theme[widget_type]['hover_color'] = hover
        ctk.ThemeManager.theme['CTkProgressBar']['progress_color'] = primary
        ctk.ThemeManager.theme['CTkOptionMenu']['fg_color'] = primary
        ctk.ThemeManager.theme['CTkOptionMenu']['button_color'] = primary
        ctk.ThemeManager.theme['CTkOptionMenu']['button_hover_color'] = hover
        ctk.ThemeManager.theme['CTkSwitch']['progress_color'] = primary
        self.apply_accent()

    def display_text(self, value):
        return redact(value, self.privacy_mode)

    def build_storage(self):
        ctk.CTkLabel(self.content, text='Physical Drive Health (read-only)',
                     text_color='gray70').pack(pady=(0, 8))
        controls = ctk.CTkFrame(self.content, fg_color='transparent')
        controls.pack(pady=5)
        self.storage_refresh_button = ctk.CTkButton(
            controls, text='Refresh Disk Health', command=self.refresh_storage)
        self.storage_refresh_button.pack(side='left', padx=5)
        if not self.admin:
            ctk.CTkButton(controls, text='Restart as Administrator',
                          command=self.request_elevation).pack(side='left', padx=5)
        self.storage_status = ctk.CTkLabel(self.content, text='Reading physical drives...',
                                           text_color='gray70')
        self.storage_status.pack(pady=8)
        self.storage_panel = ctk.CTkScrollableFrame(self.content, fg_color='transparent')
        self.storage_panel.pack(fill='both', expand=True, padx=18, pady=(0, 12))
        if self.storage_busy:
            self.storage_refresh_button.configure(state='disabled')
        else:
            self.refresh_storage()

    def refresh_storage(self):
        if self.current_page != 'Storage' or self.storage_busy:
            return
        self.storage_busy = True
        self.storage_refresh_button.configure(state='disabled')
        self.storage_status.configure(text='Reading physical drives...', text_color='gray70')
        for child in self.storage_panel.winfo_children():
            child.destroy()
        threading.Thread(target=self.storage_worker, daemon=True).start()

    def storage_worker(self):
        try:
            self.events.put(('storage_result', disk_health_snapshot()))
        except Exception:
            self.events.put(('storage_result', {'status': 'unavailable', 'disks': []}))

    @staticmethod
    def storage_value(value, suffix=''):
        return 'N/A' if value is None or value == '' else f'{value}{suffix}'

    def render_storage(self, data):
        if self.current_page != 'Storage':
            return
        self.storage_refresh_button.configure(state='normal')
        for child in self.storage_panel.winfo_children():
            child.destroy()
        status = data.get('status')
        if status != 'ok':
            messages = {'timeout': 'Disk health query timed out. Try refreshing.',
                        'unsupported_platform': 'Disk health is supported on Windows only.',
                        'invalid_response': 'Windows returned an invalid disk health response.'}
            self.storage_status.configure(text=messages.get(status, 'Disk health information unavailable.'),
                                          text_color='#f08080')
            return
        disks = data.get('disks', [])
        self.storage_status.configure(text=f'{len(disks)} physical drive(s) detected' if disks else
                                      'No physical drives detected.', text_color='gray70')
        for disk in disks:
            card = ctk.CTkFrame(self.storage_panel, corner_radius=12)
            card.pack(fill='x', padx=6, pady=7)
            value = self.storage_value
            ctk.CTkLabel(card, text=self.display_text(disk.get('model') or 'Unknown drive'),
                         font=('Segoe UI', 18, 'bold')).pack(anchor='w', padx=18, pady=(12, 4))
            size = disk.get('size_bytes')
            capacity = 'N/A' if size is None else f'{size / 1024**3:.2f} GiB'
            ctk.CTkLabel(card, text=f"{capacity}  |  {value(disk.get('media_type'))}  |  {value(disk.get('bus_type'))}",
                         text_color='gray70').pack(anchor='w', padx=18)
            health = value(disk.get('health_status'))
            color = '#70c080' if health.lower() == 'healthy' else ('gray70' if health == 'N/A' else '#e0b66a')
            ctk.CTkLabel(card, text=f"Health: {health}  |  Operational status: {value(disk.get('operational_status'))}",
                         text_color=color).pack(anchor='w', padx=18, pady=(5, 8))
            metrics = ctk.CTkFrame(card, fg_color='transparent')
            metrics.pack(fill='x', padx=18)
            metrics.grid_columnconfigure((0, 1), weight=1)
            for i, (label, key, suffix) in enumerate((
                ('Temperature', 'temperature_c', ' °C'),
                ('Reported max temperature', 'temperature_max_c', ' °C'),
                ('Reported wear', 'wear_percent', '%'),
                ('Power-on hours', 'power_on_hours', ' h'),
                ('Total read errors', 'read_errors_total', ''),
                ('Total write errors', 'write_errors_total', ''),
                ('Uncorrected read errors', 'read_errors_uncorrected', ''),
                ('Uncorrected write errors', 'write_errors_uncorrected', ''))):
                ctk.CTkLabel(metrics, text=f"{label}: {value(disk.get(key), suffix)}", anchor='w').grid(
                    row=i // 2, column=i % 2, sticky='ew', padx=4, pady=4)
            reliability = disk.get('reliability_status')
            note = {'permission_denied': 'Extended metrics require administrator access.',
                    'available': 'Extended metrics available where reported by the drive.'}.get(
                        reliability, 'Extended metrics unavailable for this drive.')
            ctk.CTkLabel(card, text=note, text_color='gray70', wraplength=650).pack(
                anchor='w', padx=18, pady=(8, 12))

    def build_network_overview(self):
        """Read-only adapter overview, refreshed off the UI thread."""
        ctk.CTkLabel(self.content, text='Network Overview',
                     font=('Segoe UI', 19, 'bold')).pack(pady=(8, 8))
        ctk.CTkLabel(self.content,
                     text='Active network adapter and connection details (read-only)',
                     text_color='gray70').pack(pady=(0, 12))
        self.network_refresh_button = ctk.CTkButton(
            self.content, text='Refresh Network Info', width=210,
            command=self.refresh_network_overview)
        self.network_refresh_button.pack(pady=(0, 12))
        self.network_status_label = ctk.CTkLabel(
            self.content, text='Ready to check network information.', text_color='gray70')
        self.network_status_label.pack(pady=(0, 12))
        panel = ctk.CTkFrame(self.content)
        panel.pack(fill='x', padx=28, pady=8)
        self.network_value_labels = {}
        for row, (key, label) in enumerate((
            ('status', 'Connection status'), ('adapter', 'Active adapter'),
            ('ipv4', 'IPv4 address'), ('gateway', 'Default gateway'),
            ('dns', 'DNS servers'), ('mac', 'MAC address'),
            ('speed', 'Adapter speed'))):
            ctk.CTkLabel(panel, text=label + ':', anchor='w',
                         font=('Segoe UI', 13, 'bold')).grid(
                             row=row, column=0, sticky='w', padx=(18, 14), pady=9)
            value = ctk.CTkLabel(panel, text='Not available', anchor='w',
                                 wraplength=480, justify='left')
            value.grid(row=row, column=1, sticky='w', padx=(0, 18), pady=9)
            self.network_value_labels[key] = value
        panel.grid_columnconfigure(1, weight=1)
        if self.network_snapshot is None:
            self.refresh_network_overview()
        else:
            self.render_network_overview(self.network_snapshot)

    def refresh_network_overview(self):
        if self.network_refreshing:
            return
        self.network_refreshing = True
        self.network_refresh_button.configure(state='disabled')
        self.network_status_label.configure(text='Reading network information...')
        threading.Thread(target=self.network_overview_worker, daemon=True).start()

    def network_overview_worker(self):
        try:
            self.events.put(('network_overview_result', get_network_overview(), None))
        except Exception as exc:
            self.events.put(('network_overview_result', None, str(exc)))

    def render_network_overview(self, data):
        if self.current_page != 'Network':
            return
        for key, label in self.network_value_labels.items():
            value = data.get(key, 'Not available')
            if key in ('ipv4', 'gateway', 'dns', 'mac') and self.privacy_mode:
                value = '[hidden]'
            else:
                value = self.display_text(value)
            label.configure(text=str(value))
        self.network_status_label.configure(text='Network information refreshed.')

    def build_settings(self):
        ctk.CTkLabel(self.content, text='Privacy & Preferences', font=('Segoe UI',19,'bold')).pack(pady=(8,15))
        switch=ctk.CTkSwitch(self.content,text='Privacy Mode',command=self.change_privacy_mode)
        switch.pack(pady=12)
        self.privacy_switch=switch
        if self.privacy_mode: switch.select()
        ctk.CTkLabel(self.content,text='Hide the computer name, Windows username, and IPv4 addresses in displayed information.',wraplength=600).pack(pady=8)
        ctk.CTkLabel(self.content,text='This does not erase existing logs, hide other applications, or guarantee that every identifier is masked.',wraplength=600,text_color='gray70').pack(pady=8)
        ctk.CTkLabel(self.content, text='Appearance', font=('Segoe UI', 19, 'bold')).pack(pady=(18, 6))
        ctk.CTkLabel(self.content, text='Accent color (applies immediately and is saved)').pack(pady=(0, 7))
        palette = ctk.CTkFrame(self.content, fg_color='transparent')
        self.accent_palette_buttons = {}
        palette.pack(pady=(0, 7))
        for name, (primary, hover) in ACCENTS.items():
            button = ctk.CTkButton(palette, text=('✓ ' if name == self.accent_color else '') + name,
                                   width=104, height=36, fg_color=primary, hover_color=hover,
                                   command=lambda selected=name: self.change_accent(selected))
            button.pack(side='left', padx=4)
            self.accent_palette_buttons[name] = button
        ctk.CTkLabel(self.content,text=f'RaksToolKit version {VERSION}').pack(pady=12)
        ctk.CTkLabel(self.content,text=self.display_text(f'Activity log: {LOG_PATH}'),wraplength=650).pack(pady=12)

    def change_privacy_mode(self):
        enabled=bool(self.privacy_switch.get())
        try: save_privacy(enabled)
        except OSError as exc:
            messagebox.showerror('Could not save setting',str(exc))
            if self.privacy_mode: self.privacy_switch.select()
            else: self.privacy_switch.deselect()
            return
        self.privacy_mode=enabled
        self.show_page('Settings')

    def build_gaming(self):
        """Scrollable gaming dashboard with asynchronous GPU sampling."""
        scroll = ctk.CTkScrollableFrame(self.content, fg_color='transparent')
        scroll.pack(fill='both', expand=True, padx=12, pady=(0, 10))
        ctk.CTkLabel(scroll, text='Gaming & Performance',
                     font=('Segoe UI', 19, 'bold')).pack(pady=(0, 5))
        self.gpu_label = ctk.CTkLabel(scroll, text='Detecting GPU...',
                                      font=('Segoe UI', 15, 'bold'), wraplength=690)
        self.gpu_label.pack(pady=(0, 5))
        self.gaming_status = ctk.CTkLabel(scroll, text='Live GPU updates every 2 seconds',
                                          text_color='gray70')
        self.gaming_status.pack(pady=(0, 12))

        metrics = ctk.CTkFrame(scroll, fg_color='transparent')
        metrics.pack(fill='x', padx=12)
        metrics.grid_columnconfigure((0, 1), weight=1, uniform='gpu')
        self.gpu_metric_values = {}
        self.gpu_metric_bars = {}
        specs = [('utilization', 'GPU Load'), ('temperature', 'Temperature'),
                 ('vram', 'VRAM Usage'), ('power', 'Power Draw')]
        for index, (key, heading) in enumerate(specs):
            card = ctk.CTkFrame(metrics, corner_radius=12)
            card.grid(row=index // 2, column=index % 2, padx=7, pady=7, sticky='nsew')
            ctk.CTkLabel(card, text=heading, text_color='gray75').pack(pady=(12, 2))
            value = ctk.CTkLabel(card, text='Checking...', font=('Segoe UI', 20, 'bold'))
            value.pack(pady=(0, 8))
            self.gpu_metric_values[key] = value
            if key in ('utilization', 'vram'):
                bar = ctk.CTkProgressBar(card)
                bar.pack(fill='x', padx=18, pady=(0, 14))
                bar.set(0)
                self.gpu_metric_bars[key] = bar
            else:
                ctk.CTkLabel(card, text='').pack(pady=(0, 8))

        clocks = ctk.CTkFrame(scroll)
        clocks.pack(fill='x', padx=19, pady=(8, 12))
        self.gpu_core_clock_label = ctk.CTkLabel(clocks, text='Core clock: Checking...')
        self.gpu_core_clock_label.pack(side='left', expand=True, padx=8, pady=10)
        self.gpu_memory_clock_label = ctk.CTkLabel(clocks, text='Memory clock: Checking...')
        self.gpu_memory_clock_label.pack(side='left', expand=True, padx=8, pady=10)

        ctk.CTkLabel(scroll, text='Gaming Utilities',
                     font=('Segoe UI', 17, 'bold')).pack(pady=(8, 6))
        self.games_label = ctk.CTkLabel(scroll, text='Known running games: Checking...', wraplength=690)
        self.games_label.pack(pady=5)
        self.latency_label = ctk.CTkLabel(scroll, text='TCP latency: Not tested')
        self.latency_label.pack(pady=5)
        actions = ctk.CTkFrame(scroll, fg_color='transparent')
        actions.pack(pady=5)
        ctk.CTkButton(actions, text='Test TCP Latency',
                      command=self.start_latency_test).pack(side='left', padx=5)
        ctk.CTkButton(actions, text='Refresh Now',
                      command=self.start_gaming_refresh).pack(side='left', padx=5)
        ctk.CTkLabel(scroll, text='Windows Power Plan',
                     font=('Segoe UI', 16, 'bold')).pack(pady=(14, 6))
        self.power_plan_menu = ctk.CTkOptionMenu(scroll, values=['Loading...'], width=300)
        self.power_plan_menu.pack(pady=4)
        apply_button = ctk.CTkButton(scroll, text='Apply Selected Power Plan',
                                     command=self.request_power_plan)
        apply_button.pack(pady=4)
        refresh_button = ctk.CTkButton(scroll, text='Refresh Power Plans',
                                       command=self.start_power_plan_refresh)
        refresh_button.pack(pady=4)
        self.power_plan_buttons = [apply_button, refresh_button]
        self.power_plan_status_label = ctk.CTkLabel(
            scroll, text=self.power_plan_status[0], text_color=self.power_plan_status[1])
        self.power_plan_status_label.pack(pady=(4, 8))
        self.update_power_plan_buttons()
        ctk.CTkLabel(scroll,
                     text='GPU metrics use NVIDIA nvidia-smi or AMD ADLX when a supported adapter is '
                          'present. Unsupported readings stay unavailable. TCP latency is not in-game ping.',
                     wraplength=690, text_color='gray70').pack(padx=25, pady=(14, 20))
        self.start_gaming_refresh()
        self.start_power_plan_refresh()

    @staticmethod
    def _gpu_fraction(value):
        try:
            return max(0.0, min(1.0, float(value.rstrip('%')) / 100))
        except (ValueError, AttributeError):
            return 0.0

    def update_gpu_cards(self, gpu):
        self.gpu_label.configure(text=self.display_text(gpu['name']))
        for key in ('utilization', 'temperature', 'vram', 'power'):
            self.gpu_metric_values[key].configure(text=self.display_text(gpu.get(key, 'Unavailable')))
        self.gpu_metric_bars['utilization'].set(self._gpu_fraction(gpu['utilization']))
        try:
            used, total = gpu['vram'].split(' / ')
            total = total.split()[0]
            fraction = float(used) / float(total)
        except (ValueError, ZeroDivisionError, AttributeError):
            fraction = 0.0
        self.gpu_metric_bars['vram'].set(max(0.0, min(1.0, fraction)))
        self.gpu_core_clock_label.configure(text=f"Core clock: {gpu['core_clock']}")
        self.gpu_memory_clock_label.configure(text=f"Memory clock: {gpu['memory_clock']}")

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

    def set_power_plan_status(self, message, color='gray70'):
        self.power_plan_status = (message, color)
        if self.current_page == 'Gaming':
            self.power_plan_status_label.configure(text=message, text_color=color)

    def update_power_plan_buttons(self):
        if self.current_page == 'Gaming':
            disabled = bool(self.running_task or self.power_plan_refresh_busy)
            for button in self.power_plan_buttons:
                button.configure(state='disabled' if disabled else 'normal')

    def start_power_plan_refresh(self):
        if self.power_plan_refresh_busy or self.running_task:
            return
        self.power_plan_refresh_busy = True
        self.set_power_plan_status('Power plan: Refreshing...', '#e0b45d')
        self.update_power_plan_buttons()
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
        self.set_power_plan_status(f'Power plan: Applying {choice}...', '#e0b45d')
        self.update_power_plan_buttons()
        self.append_log(f'--- Activating power plan: {choice} ---')
        threading.Thread(target=self.power_plan_worker_apply, args=(guid,), daemon=True).start()

    def power_plan_worker_apply(self, guid):
        try:
            activate_power_plan(guid)
            self.events.put(('power_applied',))
        except Exception as exc:
            self.events.put(('error', 'Change power plan', str(exc)))

    def build_dashboard(self):
        scroll = ctk.CTkScrollableFrame(self.content, fg_color='transparent')
        scroll.pack(fill='both', expand=True, padx=18, pady=(0, 12))
        ctk.CTkLabel(scroll, text='Live System Overview', font=('Segoe UI', 18, 'bold')).pack(pady=(0, 12))
        cards = ctk.CTkFrame(scroll, fg_color='transparent')
        cards.pack(fill='x')
        self.stats = {}
        self.hardware_graphs = {}
        primary, _ = ACCENTS.get(self.accent_color, ACCENTS[DEFAULT_ACCENT])
        for metric, title in enumerate(('CPU', 'RAM', 'C: Drive'), start=1):
            card = ctk.CTkFrame(cards)
            card.pack(side='left', expand=True, fill='both', padx=6)
            ctk.CTkLabel(card, text=title, font=('Segoe UI', 16, 'bold')).pack(pady=(18, 5))
            label = ctk.CTkLabel(card, text='Loading...', font=('Segoe UI', 22))
            label.pack(pady=5)
            bar = ctk.CTkProgressBar(card, progress_color=primary)
            bar.set(0)
            bar.pack(fill='x', padx=16, pady=(8, 6))
            background = card.cget('fg_color')
            if isinstance(background, (tuple, list)):
                background = background[1]
            graph = HardwareGraph(card, metric, accent=primary, background=background, width=120)
            graph.pack(fill='x', padx=16, pady=(4, 2))
            graph.update_history(self.hardware_history.snapshot())
            ctk.CTkLabel(card, text='Last 60 seconds', text_color='gray70',
                         font=('Segoe UI', 11)).pack(pady=(0, 8))
            self.hardware_graphs[title] = graph
            self.stats[title] = (label, bar)
        info = ctk.CTkFrame(scroll)
        info.pack(fill='x', padx=6, pady=15)
        self.dashboard_details = {}
        for title in ('Operating system', 'Processor', 'CPU cores', 'CPU frequency', 'Total memory', 'Available memory', 'Computer'):
            row = ctk.CTkFrame(info, fg_color='transparent')
            row.pack(fill='x', padx=18, pady=5)
            ctk.CTkLabel(row, text=title + ':', width=160, anchor='w').pack(side='left')
            label = ctk.CTkLabel(row, text='Loading...', anchor='w', wraplength=490)
            label.pack(side='left', fill='x', expand=True)
            self.dashboard_details[title] = label
        ctk.CTkLabel(scroll, text='Storage Volumes', font=('Segoe UI', 18, 'bold')).pack(pady=(0, 8))
        self.dashboard_status = ctk.CTkLabel(scroll, text='Reading hardware...', text_color='gray70')
        self.dashboard_status.pack()
        self.volume_panel = ctk.CTkFrame(scroll, fg_color='transparent')
        self.volume_panel.pack(fill='x', padx=6)
        self.volume_cards = {}

    def update_dashboard(self):
        if self.current_page != 'Dashboard' or self.dashboard_busy:
            return
        self.dashboard_busy = True
        threading.Thread(target=self.dashboard_worker, daemon=True).start()

    def dashboard_worker(self):
        try:
            self.events.put(('dashboard_result', system_snapshot(), volume_snapshot(), None))
        except Exception as exc:
            self.events.put(('dashboard_result', {}, [], str(exc)))

    @staticmethod
    def set_dashboard_metric(label, bar, value):
        text = format_percent(value)
        label.configure(text=text)
        bar.set(value / 100 if text != 'N/A' else 0)

    def render_dashboard(self, system, volumes, error=None):
        if self.current_page != 'Dashboard':
            return
        data = format_system(system)
        c_drive = next((v for v in volumes if v.get('device', '').rstrip('\\/').upper() == 'C:'), {})
        readings = (system.get('cpu_percent'), system.get('memory_percent'), c_drive.get('percent'))
        self.hardware_history.append(*readings)
        history = self.hardware_history.snapshot()
        for title, value in zip(('CPU', 'RAM', 'C: Drive'), readings):
            self.set_dashboard_metric(*self.stats[title], value)
            self.hardware_graphs[title].update_history(history)
        details = {'Operating system': data['os_name'], 'Processor': data['cpu_name'],
                   'CPU cores': f"{data['physical_cores']} physical / {data['logical_cores']} logical",
                   'CPU frequency': data['cpu_frequency_mhz'], 'Total memory': data['memory_total_bytes'],
                   'Available memory': data['memory_available_bytes'], 'Computer': platform.node()}
        for title, value in details.items():
            self.dashboard_details[title].configure(text=self.display_text(value))
        self.dashboard_status.configure(text='Unable to read hardware.' if error else ('No mounted volumes available.' if not volumes else f'{len(volumes)} mounted volume(s)'))
        primary, _ = ACCENTS.get(self.accent_color, ACCENTS[DEFAULT_ACCENT])
        active = set()
        for volume in volumes:
            key = (volume.get('device'), volume.get('mountpoint'))
            active.add(key)
            if key not in self.volume_cards:
                card = ctk.CTkFrame(self.volume_panel)
                card.pack(fill='x', pady=4)
                label = ctk.CTkLabel(card, text='', anchor='w')
                label.pack(fill='x', padx=14, pady=(8, 2))
                bar = ctk.CTkProgressBar(card, progress_color=primary)
                bar.pack(fill='x', padx=14, pady=(2, 10))
                self.volume_cards[key] = (card, label, bar)
            _, label, bar = self.volume_cards[key]
            v = format_volume(volume)
            label.configure(text=self.display_text(f"{v['device']}  |  {v['filesystem']}  |  {v['used_bytes']} / {v['total_bytes']} used  |  {v['free_bytes']} free  |  {v['percent']}"))
            bar.set(volume['percent'] / 100 if v['percent'] != 'N/A' else 0)
        for key in list(self.volume_cards):
            if key not in active:
                self.volume_cards.pop(key)[0].destroy()

    def refresh_gaming_live(self):
        """Poll only while the Gaming page is visible; never overlap workers."""
        if self.current_page == 'Gaming' and not self.gaming_busy:
            self.start_gaming_refresh()
        self.after(2000, self.refresh_gaming_live)

    def refresh_stats(self):
        if self.current_page == 'Dashboard':
            self.update_dashboard()
        self.after(1000, self.refresh_stats)

    def build_maintenance(self):
        if self.admin:
            ctk.CTkLabel(self.content, text='Running as Administrator', text_color='#70c080').pack(pady=(0, 10))
        else:
            primary, hover = ACCENTS.get(self.accent_color, ACCENTS[DEFAULT_ACCENT])
            ctk.CTkButton(self.content, text='Restart as Administrator',
                          fg_color=primary, hover_color=hover,
                          command=self.request_elevation).pack(pady=(0, 10))
        tabs = ctk.CTkFrame(self.content, fg_color='#454545', corner_radius=7)
        tabs.pack(padx=15, pady=(0, 10))
        self.maintenance_tab_buttons = {}
        for name in ('System Repair', 'Smart Cleanup', 'Network', 'Software Updates'):
            button = ctk.CTkButton(
                tabs, text=name, height=26, corner_radius=5,
                fg_color='#454545', hover_color='#555555',
                command=lambda selected=name: self.show_maintenance_tab(selected),
            )
            button.pack(side='left', padx=2, pady=2)
            self.maintenance_tab_buttons[name] = button
        self.tab_content = ctk.CTkFrame(self.content, fg_color='transparent')
        self.tab_content.pack(fill='x', padx=15, pady=5)
        self.maintenance_status = ctk.CTkLabel(self.content, text=self.maintenance_state[0],
                                               text_color=self.maintenance_state[1])
        self.maintenance_status.pack(pady=(4, 0))
        self.maintenance_output = ctk.CTkTextbox(self.content, height=220)
        self.maintenance_output.pack(fill='both', expand=True, padx=20, pady=(8, 20))
        self.maintenance_output.insert('end', self.display_text('\n'.join(self.maintenance_log)) + '\n')
        self.maintenance_output.configure(state='disabled')
        self.maintenance_output.see('end')
        self.show_maintenance_tab(self.current_tab)

    def update_maintenance_tab_colors(self):
        """Highlight only the active Maintenance tab using the saved accent."""
        if self.current_page != 'Maintenance':
            return
        primary, hover = ACCENTS.get(self.accent_color, ACCENTS[DEFAULT_ACCENT])
        for name, button in self.maintenance_tab_buttons.items():
            active = name == self.current_tab
            button.configure(
                fg_color=primary if active else '#454545',
                hover_color=hover if active else '#555555',
            )

    def show_maintenance_tab(self, tab):
        primary, hover = ACCENTS.get(self.accent_color, ACCENTS[DEFAULT_ACCENT])
        self.current_tab = tab
        self.update_maintenance_tab_colors()
        for widget in self.tab_content.winfo_children():
            widget.destroy()
        self.task_buttons = []
        if tab == 'System Repair':
            ctk.CTkLabel(self.tab_content, text='Windows Component & File Repair',
                         font=('Segoe UI', 17, 'bold')).pack(pady=10)
            for task in ('DISM RestoreHealth', 'SFC Scan'):
                button = ctk.CTkButton(self.tab_content, text=task, width=200, height=36,
                                       fg_color=primary, hover_color=hover,
                                       command=lambda t=task: self.start_task(t))
                button.pack(pady=6)
                self.task_buttons.append(button)
        elif tab == 'Software Updates':
            ctk.CTkLabel(self.tab_content, text='Available Application Updates',
                         font=('Segoe UI', 17, 'bold')).pack(pady=10)
            ctk.CTkLabel(self.tab_content, text='Check for available updates or install all available upgrades using winget.').pack(pady=(0, 8))
            controls = ctk.CTkFrame(self.tab_content, fg_color='transparent')
            controls.pack(pady=6)
            check_button = ctk.CTkButton(controls, text='Check for Updates', width=200, height=36,
                                         fg_color=primary, hover_color=hover,
                                         command=self.start_update_check)
            check_button.pack(side='left', padx=6)
            update_button = ctk.CTkButton(controls, text='Update All', width=200, height=36,
                                          fg_color=primary, hover_color=hover,
                                          command=self.start_upgrade_all)
            update_button.pack(side='left', padx=6)
            selected_button = ctk.CTkButton(controls, text='Update Selected', width=170, height=36,
                                            fg_color=primary, hover_color=hover,
                                            command=self.start_upgrade_selected)
            selected_button.pack(side='left', padx=6)
            self.task_buttons.extend((check_button, update_button, selected_button))
            self.update_selected_button = selected_button
            self.updates_count_label = ctk.CTkLabel(self.tab_content, text='Run Check for Updates to populate the table.', text_color='gray70')
            self.updates_count_label.pack(pady=(10, 4))
            self.updates_table = ctk.CTkScrollableFrame(self.tab_content, height=155)
            self.updates_table.pack(fill='x', padx=12, pady=(0, 6))
            self.render_available_updates()
        elif tab == 'Network':
            ctk.CTkLabel(self.tab_content, text='DNS Resolver Maintenance',
                         font=('Segoe UI', 17, 'bold')).pack(pady=10)
            button = ctk.CTkButton(self.tab_content, text='Flush DNS Cache', width=200,
                                   fg_color=primary, hover_color=hover,
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
                ctk.CTkCheckBox(self.tab_content, text=name, variable=var,
                                fg_color=primary, hover_color=hover).pack(anchor='w', padx=30, pady=3)
            controls = ctk.CTkFrame(self.tab_content, fg_color='transparent')
            controls.pack(pady=12)
            for label, mode in (('Scan', 'scan'), ('Dry Run', 'dry'), ('Clean Selected', 'clean')):
                button = ctk.CTkButton(controls, text=label, width=130,
                                       fg_color=primary, hover_color=hover,
                                       command=lambda m=mode: self.start_cleanup(m))
                button.pack(side='left', padx=5)
                self.task_buttons.append(button)
        self.update_task_buttons()
        # Tab content is created on demand, so theme its new controls immediately.
        self.apply_accent()

    def toggle_update_selection(self, package_id, enabled):
        if enabled:
            self.selected_update_ids.add(package_id)
        else:
            self.selected_update_ids.discard(package_id)
        self.update_task_buttons()

    def render_available_updates(self):
        """Render saved update results; safe to call after tab navigation."""
        if self.current_page != 'Maintenance' or self.current_tab != 'Software Updates':
            return
        for child in self.updates_table.winfo_children():
            child.destroy()
        updates = self.available_updates
        if updates is None:
            self.updates_count_label.configure(text='Run Check for Updates to populate the table.')
            self.update_task_buttons()
            return
        self.updates_count_label.configure(text=f'{len(updates)} available update(s)' if updates else 'No updates found in the recognized winget table.')
        for col, label, weight in ((0, 'Select', 0), (1, 'Application', 3), (2, 'Installed', 1), (3, 'Available', 1)):
            self.updates_table.grid_columnconfigure(col, weight=weight)
            ctk.CTkLabel(self.updates_table, text=label, font=('Segoe UI', 12, 'bold'), anchor='w').grid(row=0, column=col, sticky='ew', padx=8, pady=3)
        primary, hover = ACCENTS.get(self.accent_color, ACCENTS[DEFAULT_ACCENT])
        for index, (name, package_id, installed, available) in enumerate(updates, 1):
            selected_var = ctk.BooleanVar(value=package_id in self.selected_update_ids)
            ctk.CTkCheckBox(self.updates_table, text='', width=24, variable=selected_var,
                            fg_color=primary, hover_color=hover,
                            command=lambda pid=package_id, var=selected_var: self.toggle_update_selection(pid, var.get())
                            ).grid(row=index, column=0, sticky='w', padx=8, pady=3)
            for col, value in enumerate((f'{name}\n{package_id}', installed, available), 1):
                ctk.CTkLabel(self.updates_table, text=self.display_text(value), anchor='w', justify='left').grid(row=index, column=col, sticky='ew', padx=8, pady=3)
        self.update_task_buttons()

    def update_task_buttons(self):
        for button in self.task_buttons:
            button.configure(state='disabled' if self.running_task else 'normal')
        if (self.current_page == 'Maintenance' and self.current_tab == 'Software Updates'
                and hasattr(self, 'update_selected_button')):
            enabled = bool(self.selected_update_ids) and not self.running_task and self.available_updates is not None
            self.update_selected_button.configure(state='normal' if enabled else 'disabled',
                                                  text=f'Update Selected ({len(self.selected_update_ids)})')

    def set_maintenance_status(self, message, color='gray70'):
        """Remember status even when the Maintenance page is not visible."""
        self.maintenance_state = (message, color)
        if self.current_page == 'Maintenance':
            self.maintenance_status.configure(text=message, text_color=color)

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
            self.maintenance_output.insert('end', self.display_text(line) + '\n')
            self.maintenance_output.see('end')
            self.maintenance_output.configure(state='disabled')

    def build_activity(self):
        ctk.CTkLabel(self.content, text='Saved activity history',
                     font=('Segoe UI', 17, 'bold')).pack(pady=8)
        self.activity_status = ctk.CTkLabel(self.content, text='Loading history...', text_color='gray70')
        self.activity_status.pack(pady=(0, 2))
        self.activity_output = ctk.CTkTextbox(self.content)
        self.activity_output.pack(fill='both', expand=True, padx=20, pady=15)
        self.refresh_activity()

    def refresh_activity(self):
        try:
            content = read_recent()
            status = f'Activity history | {len(content.splitlines())} displayed lines'
        except OSError as exc:
            content = f'Unable to read log: {exc}'
            status = 'Unable to load activity history'
        self.activity_status.configure(text=status)
        self.activity_output.configure(state='normal')
        self.activity_output.delete('1.0', 'end')
        self.activity_output.insert('end', self.display_text(content))
        self.activity_output.see('end')
        self.activity_output.configure(state='disabled')

    def request_elevation(self):
        if self.running_task:
            messagebox.showwarning('Task running', 'Wait for the current task to finish.')
            return
        if not messagebox.askyesno('Administrator permissions', 'Restart RaksToolKit as administrator?'):
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
        self.set_maintenance_status(f'Running: {task}...', '#e0b66a')
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

    def start_update_check(self):
        if self.running_task:
            return
        task = 'Check for Updates'
        self.running_task = task
        self.set_maintenance_status('Checking for application updates...', '#e0b66a')
        self.update_task_buttons()
        self.available_updates = None
        self.selected_update_ids.clear()
        self.render_available_updates()
        self.append_log('\n--- Checking available updates (winget upgrade) ---')
        threading.Thread(target=self.update_check_worker, daemon=True).start()

    def update_check_worker(self):
        task = 'Check for Updates'
        try:
            captured = []
            def receive(line):
                captured.append(line)
                self.events.put(('line', line))
            code = check_updates(receive)
            self.events.put(('updates_result', code, parse_upgrade_table(captured)))
            self.events.put(('done', task, code))
        except Exception as exc:
            self.events.put(('error', task, str(exc)))

    def start_upgrade_all(self):
        if self.running_task:
            return
        if not messagebox.askyesno(
            'Confirm software upgrades',
            'Run winget upgrade --all?\n\n'
            'This may download and install updates, close running applications, '
            'request administrator permission, or require a restart. '
            'Some installers may ask for input. Save your work first.\n\n'
            'Continue?'
        ):
            return
        task = 'Update All'
        self.running_task = task
        self.set_maintenance_status('Installing available application updates...', '#e0b66a')
        self.update_task_buttons()
        self.append_log('\n--- Starting application upgrades (winget upgrade --all) ---')
        threading.Thread(target=self.upgrade_all_worker, daemon=True).start()

    def upgrade_all_worker(self):
        task = 'Update All'
        try:
            code = upgrade_all(lambda line: self.events.put(('line', line)))
            self.events.put(('done', task, code))
        except Exception as exc:
            self.events.put(('error', task, str(exc)))

    def start_upgrade_selected(self):
        if self.running_task or not self.available_updates:
            return
        selected = [item for item in self.available_updates if item[1] in self.selected_update_ids]
        if not selected:
            return
        names = '\n'.join(f'• {name} ({package_id})' for name, package_id, _, _ in selected)
        if not messagebox.askyesno(
            'Confirm selected software upgrades',
            f'Upgrade these {len(selected)} application(s)?\n\n{names}\n\n'
            'Installers may request input or administrator permission, close apps, or require a restart. '
            'Save your work before continuing.'
        ):
            return
        task = 'Update Selected'
        self.running_task = task
        self.set_maintenance_status(f'Updating {len(selected)} selected application(s)...', '#e0b66a')
        self.update_task_buttons()
        self.append_log(f'\n--- Starting {len(selected)} selected application upgrades ---')
        threading.Thread(target=self.upgrade_selected_worker, args=(selected,), daemon=True).start()

    def upgrade_selected_worker(self, selected):
        failures = 0
        try:
            for name, package_id, _, _ in selected:
                self.events.put(('line', f'--- Upgrading {name} ({package_id}) ---'))
                try:
                    code = upgrade_package(package_id, lambda line: self.events.put(('line', line)))
                except Exception as exc:
                    code = -1
                    self.events.put(('line', f'{package_id}: {exc}'))
                self.events.put(('line', f'--- {package_id}: exit code {code} ---'))
                if code != 0:
                    failures += 1
            self.events.put(('selected_upgrades_done', len(selected), failures))
        except Exception as exc:
            self.events.put(('error', 'Update Selected', str(exc)))

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
        self.set_maintenance_status(f'Running cleanup: {mode}...', '#e0b66a')
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
                if event[0] == 'dashboard_result':
                    _, system, volumes, error = event
                    self.dashboard_busy = False
                    self.render_dashboard(system, volumes, error)
                elif event[0] == 'storage_result':
                    self.storage_busy = False
                    self.render_storage(event[1])
                elif event[0] == 'network_overview_result':
                    _, data, error = event
                    self.network_refreshing = False
                    if data is not None:
                        self.network_snapshot = data
                    if self.current_page == 'Network':
                        self.network_refresh_button.configure(state='normal')
                        if error:
                            self.network_status_label.configure(text=f'Unable to read network information: {error}')
                        else:
                            self.render_network_overview(data)
                elif event[0] == 'line':
                    self.append_log(event[1])
                elif event[0] == 'updates_result':
                    _, code, parsed = event
                    self.available_updates = parsed if code == 0 else None
                    if self.available_updates is not None:
                        valid_ids = {item[1] for item in self.available_updates}
                        self.selected_update_ids.intersection_update(valid_ids)
                    if code == 0 and parsed is None:
                        self.append_log('Update table could not be parsed (possibly localized output). See raw winget output above.')
                    self.render_available_updates()
                    if self.current_page == 'Maintenance' and self.current_tab == 'Software Updates' and parsed is None:
                        self.updates_count_label.configure(text='Table unavailable. See command output below.')
                elif event[0] == 'done':
                    _, task, code = event
                    self.append_log(f'--- {task}: {"completed" if code == 0 else "failed"} (exit code {code}) ---')
                    self.set_maintenance_status(
                        f'{task}: completed successfully.' if code == 0 else f'{task}: failed (exit code {code}).',
                        '#70c080' if code == 0 else '#f08080')
                    self.running_task = None
                    self.update_task_buttons()
                elif event[0] == 'selected_upgrades_done':
                    _, total, failures = event
                    self.append_log(f'--- Update Selected: {total - failures}/{total} succeeded, {failures} failed ---')
                    self.set_maintenance_status(
                        f'Update Selected: {total - failures}/{total} succeeded. Run Check for Updates to refresh the list.',
                        '#70c080' if failures == 0 else '#f08080')
                    self.running_task = None
                    self.selected_update_ids.clear()
                    self.available_updates = None  # Never show stale results after installation.
                    self.render_available_updates()
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
                    self.set_maintenance_status(
                        'Cleanup scan completed.' if mode == 'scan' else
                        'Dry run completed; no files deleted.' if mode == 'dry' else
                        'Cleanup completed.', '#70c080')
                    self.running_task = None
                    self.update_task_buttons()
                elif event[0] == 'gaming_data':
                    self.gaming_busy = False
                    _, gpu, games = event
                    if self.current_page == 'Gaming':
                        self.gaming_status.configure(text='Gaming diagnostics updated.')
                        self.update_gpu_cards(gpu)
                        text = '; '.join(f'{name} (PID {pid}, {mib} MiB RAM)' for name, pid, mib in games)
                        self.games_label.configure(text=self.display_text('Known running games: ' + (text or 'None detected')))
                elif event[0] == 'gaming_error':
                    if event[1].startswith('Power plans:'):
                        self.power_plan_refresh_busy = False
                        self.set_power_plan_status(f'{event[1]}', '#f08080')
                        self.update_power_plan_buttons()
                    else:
                        self.gaming_busy = False
                    if self.current_page == 'Gaming':
                        self.gaming_status.configure(text=self.display_text(f'Diagnostics: {event[1]}'))
                elif event[0] == 'latency':
                    if self.current_page == 'Gaming':
                        self.latency_label.configure(text=self.display_text(f'TCP latency: {event[1]}'))
                elif event[0] == 'power_plans':
                    self.power_plan_refresh_busy = False
                    plans = event[1]
                    self.gaming_plans = {f'{name} [{guid[:8]}]': guid for guid, name, active in plans}
                    if self.current_page == 'Gaming':
                        labels = list(self.gaming_plans) or ['No power plans found']
                        self.power_plan_menu.configure(values=labels)
                        active = next((f'{name} [{guid[:8]}]' for guid, name, is_active in plans if is_active), labels[0])
                        self.power_plan_menu.set(active)
                    self.set_power_plan_status(
                        'Power plans refreshed.' if plans else 'No power plans found.',
                        '#70c080' if plans else '#f08080')
                    self.update_power_plan_buttons()
                elif event[0] == 'power_applied':
                    self.append_log('--- Power plan activated successfully ---')
                    self.set_power_plan_status('Power plan activated successfully.', '#70c080')
                    self.running_task = None
                    self.update_task_buttons()
                    self.start_power_plan_refresh()
                elif event[0] == 'error':
                    _, task, error = event
                    self.append_log(f'ERROR ({task}): {error}')
                    self.set_maintenance_status(f'{task}: failed. Check the log for details.', '#f08080')
                    if task == 'Change power plan':
                        self.set_power_plan_status(f'Power plan change failed: {error}', '#f08080')
                    self.running_task = None
                    self.update_task_buttons()
                    self.update_power_plan_buttons()
        except queue.Empty:
            pass
        self.after(100, self.process_events)


if __name__ == '__main__':
    RaksToolKit().mainloop()

# Backward-compatible alias for existing tests and integrations.
WinToolKit = RaksToolKit

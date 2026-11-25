import hashlib
import hmac
import json
import os
import threading
import time
import tkinter as tk
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

import qrcode
from PIL import Image, ImageTk

try:
    import winsound
except ImportError:  # pragma: no cover - the app is intended for Windows
    winsound = None


# ======================= CONFIGURATION =======================
APPS_SCRIPT_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbwUqM7rfAlV4InXyEPaK-tnwg-qfy2CfCNyPacLOTShT6dflIiqu8cgxVhcil6PBbfBWA/exec"
)
SECRET_KEY = "HOSPITAL_STAFF_SECRET_2024"
VALIDITY_WINDOW = 15
STAFF_DAYS = [0, 1, 3]  # Monday, Tuesday and Thursday
START_HOUR, START_MIN = 7, 30
END_HOUR, END_MIN = 8, 30

APP_NAME = "CNC Staff Presence"
DEFAULT_SETTINGS = {
    "report_email": "aryanoubeida@gmail.com",
    "test_mode": False,
    "total_staff": 30,
}
APP_DATA_DIR = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
SETTINGS_PATH = APP_DATA_DIR / "settings.json"
# =============================================================


COLORS = {
    "navy": "#071C33",
    "navy_2": "#0D2948",
    "surface": "#102A43",
    "surface_2": "#153552",
    "line": "#244765",
    "text": "#F7FAFC",
    "muted": "#A8B8CA",
    "teal": "#22D3D1",
    "teal_dark": "#0E9F9D",
    "green": "#34D399",
    "amber": "#FBBF24",
    "red": "#FB7185",
    "white": "#FFFFFF",
}


def load_settings():
    settings = DEFAULT_SETTINGS.copy()
    try:
        with SETTINGS_PATH.open("r", encoding="utf-8") as handle:
            saved = json.load(handle)
        if isinstance(saved, dict):
            settings.update(saved)
    except (OSError, ValueError, TypeError):
        pass

    settings["report_email"] = str(settings.get("report_email", "")).strip()
    settings["test_mode"] = bool(settings.get("test_mode", False))
    try:
        settings["total_staff"] = max(1, int(settings.get("total_staff", 30)))
    except (TypeError, ValueError):
        settings["total_staff"] = DEFAULT_SETTINGS["total_staff"]
    return settings


def save_settings(settings):
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    temporary_path = SETTINGS_PATH.with_suffix(".tmp")
    with temporary_path.open("w", encoding="utf-8") as handle:
        json.dump(settings, handle, ensure_ascii=False, indent=2)
    temporary_path.replace(SETTINGS_PATH)


def parse_server_response(body):
    try:
        result = json.loads(body)
    except ValueError as error:
        if "accounts.google.com" in body or "ServiceLogin" in body:
            message = "Google demande une connexion. Vérifiez l’accès public du déploiement Web."
        else:
            message = ("Le service Google renvoie une page HTML. Mettez script.js à jour, "
                       "puis Déployer > Gérer les déploiements > Nouvelle version. "
                       "Vérifiez l’URL /exec et les autorisations Mail.")
        raise RuntimeError(message) from error
    if not isinstance(result, dict):
        raise RuntimeError("Réponse inattendue du service Google.")
    return result


class StaffPresenceWidget:
    def __init__(self, root):
        self.root = root
        self.settings = load_settings()
        self.stop_event = threading.Event()
        self.banner_timer = None
        self.settings_window = None
        self.last_seen_scan_key = None
        self.has_initialized = False
        self.last_qr_step = None
        self.was_active = None
        self.qr_request_in_progress = False
        self.next_qr_request = 0.0
        self.server_clock_offset = 0.0
        self.server_time_known = False
        self.last_qr_server_time = ""
        self.last_qr_error = ""
        self.last_sync_error = ""
        self.tk_img = None
        self.move_x = 0
        self.move_y = 0

        self.root.title("WI-PRESENCE | CNC Staff Presence")
        try:
            self.root.iconbitmap(str(Path(__file__).with_name("wi-presence-icon.ico")))
        except (OSError, tk.TclError):
            pass
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=COLORS["navy"])
        self.width = 210
        self.height = 260
        self.position_bottom_right()
        self.root.protocol("WM_DELETE_WINDOW", self.close_app)
        self.root.bind("<Escape>", lambda _event: self.close_app())

        self.build_interface()
        self.update_qr_loop()
        self.start_live_sync()

    def position_bottom_right(self):
        self.root.update_idletasks()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = max(8, screen_w - self.width - 24)
        y = max(8, screen_h - self.height - 64)
        self.root.geometry(f"{self.width}x{self.height}+{x}+{y}")

    def build_interface(self):
        transparent = "#FF00FF"
        self.root.configure(bg=transparent)
        try:
            self.root.attributes("-transparentcolor", transparent)
        except tk.TclError:
            pass
        self.shell = tk.Frame(self.root, bg=transparent)
        self.shell.pack(fill="both", expand=True)

        self.qr_slot = tk.Frame(self.shell, bg=transparent)
        self.qr_slot.pack(side="bottom")
        self.qr_card = tk.Frame(
            self.qr_slot,
            bg=COLORS["white"],
            padx=8,
            pady=6,
            highlightbackground="#D7EEF0",
            highlightthickness=1,
        )
        header = tk.Frame(self.qr_card, bg=COLORS["white"])
        header.pack(fill="x")
        brand = tk.Label(header, text="CNC  •  POINTAGE", font=("Segoe UI", 9, "bold"),
                         fg=COLORS["teal_dark"], bg=COLORS["white"])
        brand.pack(side="left")
        for parent in (header, brand):
            parent.bind("<ButtonPress-1>", self.start_move)
            parent.bind("<B1-Motion>", self.do_move)
        for label, command in (("×", self.close_app), ("⚙", self.open_settings)):
            tk.Button(header, text=label, command=command, relief="flat", bd=0,
                      bg=COLORS["white"], fg=COLORS["navy"], cursor="hand2",
                      font=("Segoe UI", 11)).pack(side="right")
        self.qr_label = tk.Label(self.qr_card, bg=COLORS["white"], bd=0)
        self.qr_label.pack()
        self.timer_label = tk.Label(self.qr_card, text="", font=("Segoe UI", 8),
                                    fg=COLORS["teal_dark"], bg=COLORS["white"])
        self.timer_label.pack(pady=(2, 0))
        self.closed_card = tk.Frame(self.qr_slot, bg=COLORS["white"], padx=14, pady=12)
        self.closed_message = tk.Label(self.closed_card, text="", wraplength=210,
                                       bg=COLORS["white"], fg=COLORS["navy"], font=("Segoe UI", 9))
        self.closed_message.pack()
        tk.Button(self.closed_card, text="Paramètres", command=self.open_settings,
                  relief="flat", bg=COLORS["white"], fg=COLORS["teal_dark"]).pack(pady=6)

        self.banner = tk.Frame(self.shell, bg=COLORS["white"], padx=10, pady=8)
        self.banner_label = tk.Label(self.banner, text="", wraplength=215,
                                     font=("Segoe UI", 9, "bold"), fg=COLORS["navy"],
                                     bg=COLORS["white"], justify="left")
        self.banner_label.pack()

    def start_move(self, event):
        self.move_x = event.x_root - self.root.winfo_x()
        self.move_y = event.y_root - self.root.winfo_y()

    def do_move(self, event):
        x = event.x_root - self.move_x
        y = event.y_root - self.move_y
        self.root.geometry(f"+{x}+{y}")

    def close_app(self):
        self.stop_event.set()
        if self.banner_timer:
            self.root.after_cancel(self.banner_timer)
        self.root.destroy()

    def is_staff_active(self):
        if self.settings.get("test_mode"):
            return True
        epoch = time.time() + self.server_clock_offset if self.server_time_known else time.time()
        now = datetime.fromtimestamp(epoch, timezone.utc)
        if now.weekday() not in STAFF_DAYS:
            return False
        start_time = now.replace(hour=START_HOUR, minute=START_MIN, second=0, microsecond=0)
        end_time = now.replace(hour=END_HOUR, minute=END_MIN, second=0, microsecond=0)
        return start_time <= now <= end_time

    def generate_token(self, epoch_time):
        step = int(epoch_time // VALIDITY_WINDOW)
        return hmac.new(
            SECRET_KEY.encode("utf-8"),
            str(step).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def generate_action_token(self, action, epoch_time, email=""):
        step = int(epoch_time // VALIDITY_WINDOW)
        message = f"{action}:{email}:{step}"
        return hmac.new(
            SECRET_KEY.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def update_qr_loop(self):
        if not self.server_time_known and time.monotonic() >= self.next_qr_request and not self.qr_request_in_progress:
            self.request_qr_payload()
        active = self.is_staff_active()
        if active != self.was_active:
            self.was_active = active
            if active:
                self.root.deiconify()
                self.root.overrideredirect(True)
            else:
                self.root.overrideredirect(False)
                self.root.after_idle(self.root.iconify)
        if active:
            self.show_qr_card()
            if time.monotonic() >= self.next_qr_request and not self.qr_request_in_progress:
                self.request_qr_payload()

            if self.last_qr_server_time:
                server_now = time.time() + self.server_clock_offset
                remaining = VALIDITY_WINDOW - (int(server_now) % VALIDITY_WINDOW)
                self.timer_label.config(text=f"QR  {remaining:02d}s", fg=COLORS["teal_dark"])
            elif self.qr_request_in_progress:
                self.timer_label.config(text="Connexion...", fg=COLORS["teal_dark"])
            else:
                self.timer_label.config(text="Service indisponible", fg=COLORS["red"])
        else:
            self.show_closed_card()
            self.last_qr_step = None

        self.root.after(1000, self.update_qr_loop)

    def fetch_service(self, params, timeout=8):
        query = urllib.parse.urlencode(params)
        request = urllib.request.Request(
            f"{APPS_SCRIPT_URL}?{query}",
            headers={"User-Agent": "CNC-Staff-Presence/2.0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                result = parse_server_response(response.read().decode("utf-8"))
        except urllib.error.URLError as error:
            raise RuntimeError(
                "Connexion Google impossible. Verifiez Internet et l'URL du deploiement Apps Script."
            ) from error
        if not isinstance(result, dict):
            raise RuntimeError("Reponse inattendue du service Google.")
        return result

    def request_qr_payload(self):
        self.qr_request_in_progress = True

        def worker():
            try:
                data = self.fetch_service({"action": "getQr"}, timeout=8)
                self.root.after(0, self.apply_qr_payload, data)
            except Exception as error:
                self.root.after(0, self.qr_request_failed, str(error))

        threading.Thread(target=worker, daemon=True).start()

    def apply_qr_payload(self, data):
        self.qr_request_in_progress = False
        if not data.get("ok") or not data.get("token") or not data.get("ts"):
            self.qr_request_failed(data.get("error", "Le serveur n'a pas fourni de QR valide."))
            return

        server_timestamp = int(data["ts"])
        server_epoch = float(data.get("serverEpoch", server_timestamp))
        url = f"{APPS_SCRIPT_URL}?{urllib.parse.urlencode({'token': data['token'], 'ts': server_timestamp})}"
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=2,
            border=3,
        )
        qr.add_data(url)
        qr.make(fit=True)
        image = qr.make_image(fill_color=COLORS["navy"], back_color=COLORS["white"]).convert("RGB")
        self.tk_img = ImageTk.PhotoImage(image)
        self.qr_label.config(image=self.tk_img)
        self.server_clock_offset = server_epoch - time.time()
        self.server_time_known = True
        self.last_qr_server_time = str(data.get("serverTime", ""))
        self.last_qr_error = ""
        self.last_qr_step = server_timestamp // VALIDITY_WINDOW
        self.next_qr_request = time.monotonic() + 12

    def qr_request_failed(self, message):
        self.qr_request_in_progress = False
        self.last_qr_error = str(message or "Erreur QR inconnue")
        self.next_qr_request = time.monotonic() + 5

    def show_qr_card(self):
        if self.closed_card.winfo_manager():
            self.closed_card.pack_forget()
        if not self.qr_card.winfo_manager():
            self.qr_card.pack(fill="x", pady=(0, 0))

    def show_closed_card(self):
        if self.qr_card.winfo_manager():
            self.qr_card.pack_forget()
        if not self.closed_card.winfo_manager():
            self.closed_card.pack(fill="x", pady=(0, 0))
        if self.settings.get("test_mode"):
            message = "Le mode test est actif. Le QR code reste disponible toute la journée."
        else:
            message = "Le QR code apparait pendant la plage de pointage : lundi, mardi et jeudi, 07:30-08:30 GMT."
        self.closed_message.config(text=message)

    def play_hospital_chime(self):
        if not winsound:
            return

        def play():
            try:
                winsound.Beep(1046, 100)
                winsound.Beep(1318, 180)
            except Exception:
                pass

        threading.Thread(target=play, daemon=True).start()

    def trigger_scan_notification(self, name, time_str):
        self.play_hospital_chime()
        self.banner_label.config(text=f"  {name} enregistré à {time_str} GMT  ")
        self.banner.place(relx=1, y=0, anchor="ne")
        self.banner.lift()
        if self.banner_timer:
            self.root.after_cancel(self.banner_timer)
        self.banner_timer = self.root.after(4500, self.banner.place_forget)

    def start_live_sync(self):
        def sync_worker():
            while not self.stop_event.is_set():
                try:
                    data = self.fetch_service({"action": "getLiveStatus"}, timeout=8)
                    if data.get("ok", True) and "count" in data:
                        self.last_sync_error = ""
                        self.root.after(0, self.apply_live_data, data)
                    elif data.get("error"):
                        self.last_sync_error = str(data["error"])
                except Exception as error:
                    self.last_sync_error = str(error)
                self.stop_event.wait(5)

        threading.Thread(target=sync_worker, daemon=True).start()

    def apply_live_data(self, data):
        last = data.get("lastScan")
        if last:
            scan_key = f"{last.get('name', '')}_{last.get('time', '')}"
            if not self.has_initialized:
                self.last_seen_scan_key = scan_key
                self.has_initialized = True
            elif self.last_seen_scan_key != scan_key:
                self.trigger_scan_notification(last.get("name", "Staff"), last.get("time", ""))
                self.last_seen_scan_key = scan_key
        else:
            self.has_initialized = True
            self.last_seen_scan_key = None

    def perform_audit(self):
        data = self.fetch_service({"action": "audit"}, timeout=10)
        if not data.get("ok"):
            raise RuntimeError(data.get("error", "Le serveur a refuse le diagnostic."))

        server_epoch = float(data.get("serverEpoch", 0))
        local_epoch = time.time()
        drift = server_epoch - local_epoch
        server_time = str(data.get("serverTime", "inconnue"))
        local_time = datetime.fromtimestamp(local_epoch, timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        qr_status = "OK - QR emis par le serveur Google" if self.last_qr_server_time else "En attente du prochain QR"
        return (
            "Diagnostic WI-PRESENCE\n"
            "Service Google : OK\n"
            f"Heure serveur : {server_time} ({data.get('timezone', 'inconnue')})\n"
            f"Heure PC : {local_time}\n"
            f"Ecart PC/serveur : {drift:+.1f} s\n"
            f"QR : {qr_status}\n"
            f"Planning : {data.get('schedule', 'inconnu')}\n"
            f"Lignes de presence : {data.get('presenceRows', '?')}\n"
            f"Telephones connus : {data.get('registeredPhones', '?')}\n"
            f"Derniere erreur QR : {self.last_qr_error or 'Aucune'}\n"
            f"Derniere erreur synchro : {self.last_sync_error or 'Aucune'}"
        )


    def open_settings(self):
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.lift()
            return

        window = tk.Toplevel(self.root)
        self.settings_window = window
        settings_bg = "#F4F7FA"
        settings_surface = "#EAF5F5"
        settings_text = COLORS["navy"]
        settings_muted = "#5B7085"
        window.title("Paramètres — CNC Staff Presence")
        window.configure(bg=settings_bg)
        window.resizable(False, False)
        window.transient(self.root)
        window.grab_set()

        panel = tk.Frame(window, bg=settings_bg, padx=22, pady=20)
        panel.pack(fill="both", expand=True)
        tk.Label(
            panel,
            text="Paramètres du pointage",
            font=("Segoe UI", 16, "bold"),
            fg=settings_text,
            bg=settings_bg,
        ).pack(anchor="w")
        tk.Label(
            panel,
            text="Ces réglages sont enregistrés sur cet ordinateur.",
            font=("Segoe UI", 9),
            fg=settings_muted,
            bg=settings_bg,
        ).pack(anchor="w", pady=(4, 18))

        tk.Label(panel, text="E-mail du rapport PDF", font=("Segoe UI", 9, "bold"), fg=settings_muted, bg=settings_bg).pack(anchor="w")
        email_var = tk.StringVar(value=self.settings.get("report_email", ""))
        email_entry = tk.Entry(
            panel,
            textvariable=email_var,
            width=38,
            relief="flat",
            bd=0,
            font=("Segoe UI", 10),
            fg=COLORS["navy"],
            bg=COLORS["white"],
            insertbackground=COLORS["navy"],
        )
        email_entry.pack(fill="x", ipady=8, pady=(6, 14))

        total_var = tk.StringVar(value=str(self.settings.get("total_staff", 30)))
        tk.Label(panel, text="Effectif attendu", font=("Segoe UI", 9, "bold"), fg=settings_muted, bg=settings_bg).pack(anchor="w")
        total_entry = tk.Entry(
            panel,
            textvariable=total_var,
            width=10,
            relief="flat",
            bd=0,
            font=("Segoe UI", 10),
            fg=COLORS["navy"],
            bg=COLORS["white"],
        )
        total_entry.pack(anchor="w", ipady=8, pady=(6, 14))

        test_var = tk.BooleanVar(value=self.settings.get("test_mode", False))
        tk.Checkbutton(
            panel,
            text="Activer le mode test (QR disponible en permanence)",
            variable=test_var,
            font=("Segoe UI", 9),
            fg=settings_text,
            bg=settings_bg,
            activeforeground=settings_text,
            activebackground=settings_bg,
            selectcolor=settings_surface,
            highlightthickness=0,
        ).pack(anchor="w", pady=(0, 14))

        schedule = tk.Frame(panel, bg=settings_surface, padx=12, pady=10)
        schedule.pack(fill="x", pady=(0, 14))
        tk.Label(
            schedule,
            text="Planning production",
            font=("Segoe UI", 8, "bold"),
            fg=COLORS["teal_dark"],
            bg=settings_surface,
        ).pack(anchor="w")
        tk.Label(
            schedule,
            text="Lundi / Mardi / Jeudi   |   07:30-08:30 GMT",
            font=("Segoe UI", 9),
            fg=settings_text,
            bg=settings_surface,
        ).pack(anchor="w", pady=(3, 0))

        feedback = tk.Label(panel, text="", wraplength=360, justify="left", font=("Segoe UI", 9), fg=settings_muted, bg=settings_bg)
        feedback.pack(fill="x", pady=(0, 8))

        def run_audit():
            audit_button.config(state="disabled")
            audit_text.config(text="Diagnostic en cours...", fg=COLORS["muted"])

            def audit_worker():
                try:
                    report = self.perform_audit()
                    color = COLORS["teal"]
                except Exception as error:
                    report = "Diagnostic impossible\n" + str(error)
                    color = COLORS["red"]

                def finish():
                    if window.winfo_exists():
                        audit_text.config(text=report, fg=color)
                        audit_button.config(state="normal")

                self.root.after(0, finish)

            threading.Thread(target=audit_worker, daemon=True).start()

        audit_button = tk.Button(
            panel,
            text="Lancer le diagnostic",
            command=run_audit,
            relief="flat",
            bd=0,
            cursor="hand2",
            font=("Segoe UI", 9, "bold"),
            fg=COLORS["navy"],
            bg="#D7EEF0",
            activebackground="#BCE3E5",
            padx=10,
            pady=6,
        )
        audit_button.pack(anchor="w", pady=(0, 6))
        audit_text = tk.Label(
            panel,
            text="Le diagnostic verifie le serveur, l'heure, le QR et la synchronisation.",
            wraplength=360,
            justify="left",
            font=("Segoe UI", 8),
            fg=settings_muted,
            bg=settings_bg,
        )
        audit_text.pack(fill="x", pady=(0, 10))

        actions = tk.Frame(panel, bg=settings_bg)
        actions.pack(fill="x")

        def save_from_dialog():
            email = email_var.get().strip()
            if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
                feedback.config(text="Veuillez saisir une adresse e-mail valide.", fg=COLORS["red"])
                return
            try:
                total = max(1, int(total_var.get().strip()))
            except ValueError:
                feedback.config(text="L’effectif doit être un nombre entier.", fg=COLORS["red"])
                return

            updated = {**self.settings, "report_email": email, "total_staff": total, "test_mode": bool(test_var.get())}
            try:
                save_settings(updated)
            except OSError as error:
                feedback.config(text=f"Impossible d’enregistrer : {error}", fg=COLORS["red"])
                return
            self.settings = updated
            feedback.config(text="Réglages enregistrés. Synchronisation de l’e-mail…", fg=COLORS["teal"])
            self.last_qr_step = None
            save_button.config(state="disabled")

            def sync_email():
                try:
                    self.report_action("setReportEmail", email)
                    message, color = "Réglages et e-mail enregistrés.", COLORS["green"]
                except Exception:
                    message, color = "Réglages locaux enregistrés. E-mail serveur à resynchroniser.", COLORS["amber"]

                def finish():
                    if window.winfo_exists():
                        feedback.config(text=message, fg=color)
                        save_button.config(state="normal")

                self.root.after(0, finish)

            threading.Thread(target=sync_email, daemon=True).start()

        def send_report_from_dialog():
            email = email_var.get().strip()
            if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
                feedback.config(text="Veuillez saisir une adresse e-mail valide.", fg=COLORS["red"])
                return
            feedback.config(text="Génération et envoi du rapport en cours…", fg=COLORS["teal"])
            send_button.config(state="disabled")

            def worker():
                try:
                    result = self.report_action("sendReport", email)
                    message = f"Rapport envoyé à {result.get('recipient', email)}."
                    color = COLORS["green"]
                except Exception as error:
                    message = f"Échec de l’envoi : {error}"
                    color = COLORS["red"]

                def finish():
                    if window.winfo_exists():
                        feedback.config(text=message, fg=color)
                        send_button.config(state="normal")

                self.root.after(0, finish)

            threading.Thread(target=worker, daemon=True).start()

        save_button = tk.Button(
            actions,
            text="Enregistrer",
            command=save_from_dialog,
            relief="flat",
            bd=0,
            cursor="hand2",
            font=("Segoe UI", 9, "bold"),
            fg=COLORS["navy"],
            bg=COLORS["teal"],
            activebackground=COLORS["teal_dark"],
            activeforeground=COLORS["white"],
            padx=12,
            pady=8,
        )
        save_button.pack(side="left")
        send_button = tk.Button(
            actions,
            text="Envoyer le rapport maintenant",
            command=send_report_from_dialog,
            relief="flat",
            bd=0,
            cursor="hand2",
            font=("Segoe UI", 9, "bold"),
            fg=COLORS["white"],
            bg=COLORS["teal_dark"],
            activebackground="#087C7A",
            activeforeground=COLORS["white"],
            padx=10,
            pady=8,
        )
        send_button.pack(side="right")

        email_entry.focus_set()

    def report_action(self, action, email):
        clock_data = self.fetch_service({"action": "audit"}, timeout=10)
        if not clock_data.get("ok") or not clock_data.get("serverEpoch"):
            raise RuntimeError(clock_data.get("error", "Le serveur n'a pas fourni son heure."))
        server_timestamp = int(float(clock_data["serverEpoch"]))
        result = self.fetch_service(
            {
                "action": action,
                "email": email,
                "ts": server_timestamp,
                "token": self.generate_action_token(action, server_timestamp, email),
            },
            timeout=30,
        )
        if not result.get("ok"):
            raise RuntimeError(result.get("error", "Reponse invalide du serveur"))
        return result



if __name__ == "__main__":
    root = tk.Tk()
    StaffPresenceWidget(root)
    root.mainloop()

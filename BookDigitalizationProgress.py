"""
tinkerchecker_v6.py
Monitor per lo stato di avanzamento dei progetti di digitalizzazione.

Uso: python tinkerchecker_v6.py
Dipendenze: solo libreria standard Python 3 (tkinter incluso).
AcquireQR è opzionale: se assente il bottone QR viene disabilitato.
"""

import csv
import json
import os
import tkinter as tk
from tkinter import filedialog, messagebox

# --- Importazione opzionale AcquireQR ---
try:
    from AcquireQR import acquireQR as _acquireQR
except ImportError:
    _acquireQR = None


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def count_files(folder: str, extension: str) -> int:
    """Conta i file con l'estensione indicata nella cartella. Ritorna 0 se assente."""
    try:
        return sum(1 for f in os.listdir(folder) if f.endswith("." + extension))
    except FileNotFoundError:
        return 0


def parse_int_entry(entry: tk.Entry) -> int:
    """Legge un campo Entry e ritorna int, oppure 0 se non è un numero."""
    val = entry.get().strip()
    return int(val) if val.isdigit() else 0


def build_acquisition_label(row: dict) -> str:
    """Costruisce la stringa descrittiva di una riga del CSV."""
    numerazione = row.get("numerazione_A", "")
    if numerazione:
        numerazione = f"({numerazione})"
    return (
        f"{row.get('descrizione', '')} "
        f"{row.get('tipo', '')}{row.get('elemento', '')}"
        f"{row.get('sottoelemento', '')}{numerazione}"
    ).strip()


def get_acquisition_status(acquisitions: list, current_count: int) -> tuple:
    """
    Dato l'elenco previsto e il conteggio attuale dei file acquisiti,
    ritorna (totale_previsto, etichetta_corrente, hint).
    """
    total = len(acquisitions)
    label = ""
    hint  = ""

    if current_count < total:
        label = build_acquisition_label(acquisitions[current_count])
    elif current_count == total:
        hint = "✅"
    else:
        extra = current_count - total
        hint  = f"⚠️ {extra} acquisizione{'' if extra == 1 else 'i'} in più."

    return total, label, hint


# ---------------------------------------------------------------------------
# Classe principale
# ---------------------------------------------------------------------------

class ScanChecker:

    FONT_SIZE          = 22
    SUBFOLDERS         = ["Recto", "Dorso e tagli", "Target", "Verso", "Inserti"]
    UPDATE_INTERVAL_MS = 1000

    def __init__(self):
        self.recto: list      = []
        self.verso: list      = []
        self.loaded: bool     = False
        self._last_segnatura  = ""
        self.working_dir: str = os.path.expanduser("~")

        self._build_ui()
        self._schedule_update()
        self.win.mainloop()

    # ------------------------------------------------------------------
    # Costruzione UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        self.win = tk.Tk()
        self.win.title("Scan Checker")
        self.win.minsize(620, 560)
        self.win.resizable(True, True)

        # --- Riga 0: Cartella di lavoro ---
        self.tk_workdir = tk.StringVar(value=f"📁 {self.working_dir}")
        tk.Button(self.win, text="Cartella di lavoro…", command=self._scegli_cartella_lavoro) \
            .grid(row=0, column=0, padx=4, pady=6, sticky="e")
        tk.Label(self.win, textvariable=self.tk_workdir, anchor="w", fg="#555") \
            .grid(row=0, column=1, columnspan=3, sticky="w", padx=4)

        # --- Riga 1: Segnatura e formato ---
        tk.Label(self.win, text="Segnatura:").grid(row=1, column=0, sticky="e", padx=4, pady=4)
        self.segnatura = tk.Entry(self.win, width=20)
        self.segnatura.grid(row=1, column=1, sticky="w", padx=4)

        tk.Label(self.win, text="Formato file:").grid(row=1, column=2, sticky="e", padx=4)
        self.file_format = tk.Entry(self.win, width=8)
        self.file_format.insert(tk.END, "IIQ")
        self.file_format.grid(row=1, column=3, sticky="w", padx=4)

        # --- Riga 2: Tagli e targets ---
        tk.Label(self.win, text="Tagli:").grid(row=2, column=0, sticky="e", padx=4, pady=4)
        self.tagli = tk.Entry(self.win, width=6)
        self.tagli.insert(tk.END, "4")
        self.tagli.grid(row=2, column=1, sticky="w", padx=4)

        tk.Label(self.win, text="Targets:").grid(row=2, column=2, sticky="e", padx=4)
        self.targets = tk.Entry(self.win, width=6)
        self.targets.insert(tk.END, "3")
        self.targets.grid(row=2, column=3, sticky="w", padx=4)

        # --- Riga 3: Checkbox ---
        self.glass            = tk.IntVar()
        self.black_background = tk.IntVar()
        self.white_background = tk.IntVar()
        self.target_in_scene  = tk.IntVar()

        tk.Checkbutton(self.win, text="vetro",          variable=self.glass).grid(row=3, column=0)
        tk.Checkbutton(self.win, text="sfondo nero",    variable=self.black_background).grid(row=3, column=1)
        tk.Checkbutton(self.win, text="sfondo bianco",  variable=self.white_background).grid(row=3, column=2)
        tk.Checkbutton(self.win, text="target in scena",variable=self.target_in_scene).grid(row=3, column=3)

        # --- Riga 4: Bottoni azione ---
        self.btn_qr = tk.Button(
            self.win, text="Acquisisci QR",
            command=self._acquire_qr,
            state=tk.NORMAL if _acquireQR else tk.DISABLED
        )
        self.btn_qr.grid(row=4, column=0, pady=6, padx=4)

        tk.Button(self.win, text="Genera struttura", command=self._genera_struttura) \
            .grid(row=4, column=1, padx=4)
        tk.Button(self.win, text="Carica lista", command=self._carica_lista) \
            .grid(row=4, column=2, padx=4)

        self.tk_csv_status = tk.StringVar(value="CSV:🔴")
        tk.Label(self.win, textvariable=self.tk_csv_status, font=("Helvetica", 16)) \
            .grid(row=4, column=3, padx=4)

        # --- Area contatori ---
        frame = tk.Frame(self.win, bd=1, relief=tk.SUNKEN)
        frame.grid(row=5, column=0, columnspan=4, sticky="nsew", padx=8, pady=8)
        self.win.grid_rowconfigure(5, weight=1)
        self.win.grid_columnconfigure(1, weight=1)

        font = ("Helvetica", self.FONT_SIZE)
        self.tk_targets  = tk.StringVar(value="Targets: —")
        self.tk_tagli    = tk.StringVar(value="Tagli: —")
        self.tk_recto    = tk.StringVar(value="Recto: —")
        self.tk_verso    = tk.StringVar(value="Verso: —")
        self.tk_progress = tk.StringVar(value="Completezza: —")

        tk.Label(frame, textvariable=self.tk_targets,  font=font, anchor="w").pack(fill="x", padx=10, pady=2)
        tk.Label(frame, textvariable=self.tk_tagli,    font=font, anchor="w").pack(fill="x", padx=10, pady=2)
        tk.Label(frame, textvariable=self.tk_recto,    font=font, anchor="w").pack(fill="x", padx=10, pady=2)
        tk.Label(frame, textvariable=self.tk_verso,    font=font, anchor="w").pack(fill="x", padx=10, pady=2)
        tk.Label(frame, textvariable=self.tk_progress,
                 font=("Helvetica", self.FONT_SIZE - 2), anchor="w").pack(fill="x", padx=10, pady=6)

    # ------------------------------------------------------------------
    # Comandi bottoni
    # ------------------------------------------------------------------

    def _scegli_cartella_lavoro(self):
        """Apre un dialogo per scegliere la cartella di lavoro."""
        path = filedialog.askdirectory(
            title="Seleziona cartella di lavoro",
            initialdir=self.working_dir
        )
        if path:
            self.working_dir = path
            self.tk_workdir.set(f"📁 {path}")
            self.loaded = False  # forza ricaricamento con il nuovo path

    def _acquire_qr(self):
        """Legge un codice QR e popola il campo segnatura."""
        try:
            label = _acquireQR()
            self.segnatura.delete(0, tk.END)
            self.segnatura.insert(0, label[:7])
        except Exception as exc:
            messagebox.showerror("Errore QR", f"Lettura QR fallita:\n{exc}")

    def _genera_struttura(self):
        """Crea la struttura di cartelle e il file session.json per un nuovo codice."""
        codexid = self.segnatura.get().strip()
        if not codexid:
            messagebox.showwarning("Campo vuoto", "Inserire una segnatura prima di generare la struttura.")
            return

        full_path = os.path.join(self.working_dir, codexid)
        if os.path.exists(full_path):
            messagebox.showwarning("Struttura esistente", f"La cartella '{full_path}' esiste già.")
            return

        targets = parse_int_entry(self.targets)
        tagli   = parse_int_entry(self.tagli)

        os.mkdir(full_path)
        for sub in self.SUBFOLDERS:
            os.mkdir(os.path.join(full_path, sub))

        session_data = {
            "targets": targets,
            "tagli": tagli,
            "glass": self.glass.get(),
            "black_background": self.black_background.get(),
            "white_background": self.white_background.get(),
            "target_in_scene": self.target_in_scene.get(),
        }
        with open(os.path.join(full_path, "session.json"), "w", encoding="utf-8") as f:
            json.dump(session_data, f, indent=2)

        self.loaded = False
        print(f"Struttura creata: {full_path}")

    def _carica_lista(self):
        """Carica il CSV di pianificazione dalla cartella della segnatura corrente."""
        codexid   = self.segnatura.get().strip()
        full_path = os.path.join(self.working_dir, codexid)

        if not os.path.isdir(full_path):
            self.tk_csv_status.set("CSV:🔴")
            return

        csv_files = [f for f in os.listdir(full_path) if f.endswith(".csv")]
        if len(csv_files) != 1:
            print(f"Lista non caricata: trovati {len(csv_files)} file CSV (atteso 1).")
            self.tk_csv_status.set("CSV:🔴")
            return

        self.recto = []
        self.verso = []
        with open(os.path.join(full_path, csv_files[0]), newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                sotto = row.get("sottoelemento", "")
                if sotto == "r":
                    self.recto.append(row)
                elif sotto == "v":
                    self.verso.append(row)

        self.loaded = True
        self.tk_csv_status.set("CSV:🟢")
        print(f"CSV caricato: {len(self.recto)} recto, {len(self.verso)} verso.")

    # ------------------------------------------------------------------
    # Loop di aggiornamento
    # ------------------------------------------------------------------

    def _schedule_update(self):
        self.win.after(self.UPDATE_INTERVAL_MS, self._update)

    def _update(self):
        segnatura = self.segnatura.get().strip()

        # Reset se la segnatura cambia
        if segnatura != self._last_segnatura:
            self.loaded = False
            self._last_segnatura = segnatura

        base         = os.path.join(self.working_dir, segnatura)
        session_path = os.path.join(base, "session.json")

        # Caricamento automatico se non ancora caricato
        if not self.loaded:
            if os.path.isfile(session_path):
                try:
                    with open(session_path, encoding="utf-8") as f:
                        data = json.load(f)
                    self.targets.delete(0, tk.END)
                    self.targets.insert(0, str(data.get("targets", 3)))
                    self.tagli.delete(0, tk.END)
                    self.tagli.insert(0, str(data.get("tagli", 4)))
                except (json.JSONDecodeError, OSError) as exc:
                    print(f"Errore lettura session.json: {exc}")
            self._carica_lista()

        tagli   = parse_int_entry(self.tagli)
        targets = parse_int_entry(self.targets)
        fmt     = self.file_format.get().strip()

        cr_r  = count_files(os.path.join(base, "Recto"),         fmt)
        cr_v  = count_files(os.path.join(base, "Verso"),         fmt)
        cr_tg = count_files(os.path.join(base, "Target"),        fmt)
        cr_ta = count_files(os.path.join(base, "Dorso e tagli"), fmt)

        # --- Recto ---
        total_r, label_r, hint_r = get_acquisition_status(self.recto, cr_r)
        self.tk_recto.set(f"Recto: {cr_r}/{total_r}  {label_r} {hint_r}".strip())

        # --- Verso ---
        verso_rev = list(reversed(self.verso))
        total_v, label_v, hint_v = get_acquisition_status(verso_rev, cr_v)
        recto_rev = list(reversed(self.recto))
        _, label_rv, hint_rv = get_acquisition_status(recto_rev, max(cr_v - 1, 0))
        self.tk_verso.set(
            f"Verso: {cr_v}/{total_v}  {label_v} {hint_v}\n"
            f"  (recto corrispondente: {label_rv} {hint_rv})".strip()
        )

        # --- Target e tagli ---
        def counter_label(name, count, expected):
            next_label = f"→ #{count + 1}" if count < expected else "✅"
            over = f" ⚠️ +{count - expected}" if count > expected else ""
            return f"{name}: {count}/{expected}  {next_label}{over}"

        self.tk_targets.set(counter_label("Target", cr_tg, targets))
        self.tk_tagli.set(counter_label("Tagli",  cr_ta, tagli))

        # --- Completezza ---
        acqu_tot = len(self.recto) + len(self.verso) + tagli + targets
        tot_now  = cr_r + cr_v + cr_tg + cr_ta

        if acqu_tot > 0:
            prc = tot_now / acqu_tot * 100
            self.tk_progress.set(f"Completezza: {tot_now}/{acqu_tot}  ({prc:.1f}%)")
        else:
            self.tk_progress.set("Completezza: — (nessuna lista caricata)")

        self._schedule_update()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ScanChecker()

import calendar as _cal
import csv
import datetime
import math
import os
import re
import sys
sys.stdout.reconfigure(encoding='utf-8')
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

_main_tk_root     = None
_progress_widgets = {}
LAST_DIR_FILE     = os.path.join(os.path.expanduser('~'), '.simcenter_csv_converter_last_dir.txt')
_TS_SAMPLE_ROWS   = 10

# ── Session-level date/year cache (reset each time the script starts) ─────────
# Stores the recording date/year chosen for the FIRST file of each timestamp
# type so that subsequent files of the same type reuse it automatically.
_session_ddd_year        = None   # int  – confirmed year for DDD files
_session_seconds_date    = None   # datetime.date or False (False = user chose Skip)

# ── Directory helpers ────────────────────────────────────────────────────────
def get_last_used_directory():
    if os.path.exists(LAST_DIR_FILE):
        try:
            with open(LAST_DIR_FILE, 'r') as f:
                last_dir = f.readline().strip()
                if os.path.isdir(last_dir):
                    return last_dir
        except Exception:
            pass
    return None

def set_last_used_directory(path):
    try:
        with open(LAST_DIR_FILE, 'w') as f:
            f.write(path)
    except Exception:
        pass

def get_main_tk_root():
    global _main_tk_root
    if _main_tk_root is None:
        _main_tk_root = tk.Tk()
        _main_tk_root.withdraw()
    return _main_tk_root

# ── Regex patterns ───────────────────────────────────────────────────────────
_RE_DDD_FORMAT             = re.compile(r'^\d{3}:\d{2}:\d{2}:\d{2}(?:\.\d+)?$')
_RE_SECONDS_SINCE_MIDNIGHT = re.compile(r'^\d+\.\d+$')

# ── Timestamp type detection ─────────────────────────────────────────────────
def _detect_timestamp_type(first_data_value):
    v = first_data_value.strip()
    if _RE_DDD_FORMAT.match(v):
        return 'DDD'
    if _RE_SECONDS_SINCE_MIDNIGHT.match(v):
        try:
            fval = float(v)
            if 0.0 < fval < 86400.0:
                return 'SECONDS'
        except ValueError:
            pass
    return None

# ── DDD parser ───────────────────────────────────────────────────────────────
def _parse_ddd_timestamp(ts_str):
    parts = ts_str.strip().split(':')
    if len(parts) != 4:
        raise ValueError(f"Expected DDD:HH:MM:SS format, got '{ts_str}'")
    return int(parts[0]), int(parts[1]), int(parts[2]), float(parts[3])

def _ddd_to_seconds(ts_str):
    _, hh, mm, ss = _parse_ddd_timestamp(ts_str)
    return hh * 3600.0 + mm * 60.0 + ss

# ── Seconds-since-midnight decoder ───────────────────────────────────────────
def _seconds_since_midnight_to_hms(t):
    hh = math.floor(t / 3600)
    mm = math.floor((t % 3600) / 60)
    ss = t % 60
    return hh, mm, ss

# ── Sample rate estimator ────────────────────────────────────────────────────
def estimate_sample_rate_from_timestamps(input_filepath, ts_type, n_samples=_TS_SAMPLE_ROWS):
    if ts_type not in ('DDD', 'SECONDS'):
        return None, None, 0, None
    timestamps_seconds = []
    try:
        with open(input_filepath, 'r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                if not row:
                    continue
                raw = row[0].strip()
                try:
                    t_sec = _ddd_to_seconds(raw) if ts_type == 'DDD' else float(raw)
                    timestamps_seconds.append(t_sec)
                except (ValueError, IndexError):
                    continue
                if len(timestamps_seconds) >= n_samples + 1:
                    break
    except Exception:
        return None, None, 0, None
    if len(timestamps_seconds) < 2:
        return None, None, 0, None
    deltas = [timestamps_seconds[i+1] - timestamps_seconds[i]
              for i in range(len(timestamps_seconds) - 1)]
    deltas = [d for d in deltas if d > 0]
    if not deltas:
        return None, None, 0, None
    deltas_sorted = sorted(deltas)
    median_delta  = deltas_sorted[len(deltas_sorted) // 2]
    filtered = [d for d in deltas if abs(d - median_delta) / median_delta <= 0.05]
    if not filtered:
        filtered = deltas
    avg_delta = sum(filtered) / len(filtered)
    raw_hz    = 1.0 / avg_delta
    if len(filtered) >= 5:
        variance   = sum((d - avg_delta) ** 2 for d in filtered) / len(filtered)
        cv         = math.sqrt(variance) / avg_delta
        confidence = 'HIGH' if cv < 0.01 else ('MEDIUM' if cv < 0.05 else 'LOW')
    elif len(filtered) >= 2:
        confidence = 'MEDIUM'
    else:
        confidence = 'LOW'
    standard_freqs = [
        1, 2, 4, 5, 8, 10, 16, 20, 25, 32, 40, 50, 64, 100, 128, 200,
        250, 256, 400, 500, 512, 1000, 1024, 2000, 2048, 4000, 4096,
        5000, 6400, 7500, 8000, 10000, 12800, 16000, 20000, 25000,
        25600, 32000, 40000, 48000, 51200, 65536, 96000, 102400
    ]
    snapped_hz = raw_hz
    for sf in standard_freqs:
        if abs(raw_hz - sf) / sf <= 0.01:
            snapped_hz = float(sf)
            break
    return snapped_hz, avg_delta, len(filtered), confidence

# ── Year prompt (DDD flow) ───────────────────────────────────────────────────
def _ask_recording_year(root, context_label, default_year=None):
    if default_year is None:
        default_year = datetime.date.today().year
    result = {'year': default_year}
    dialog = tk.Toplevel(root)
    dialog.title('Confirm Recording Year')
    dialog.resizable(False, False)
    dialog.grab_set()

    ttk.Label(dialog, text='Recording Year',
              font=('Arial', 11, 'bold')).grid(
        row=0, column=0, columnspan=3, pady=(14, 4), padx=18, sticky='w')
    ttk.Label(dialog,
              text=(f'Detected timestamp: {context_label}\n'
                    f'The current year ({default_year}) has been assumed.\n'
                    'Please confirm or enter the correct recording year below.'),
              justify='left', wraplength=360).grid(
        row=1, column=0, columnspan=3, padx=18, pady=(0, 10), sticky='w')

    ttk.Label(dialog, text='Year:', font=('Arial', 10)).grid(
        row=2, column=0, padx=(18, 6), pady=6, sticky='w')
    year_var = tk.StringVar(value=str(default_year))
    year_entry = ttk.Entry(dialog, textvariable=year_var, width=8, font=('Arial', 11))
    year_entry.grid(row=2, column=1, padx=4, pady=6, sticky='w')
    year_entry.select_range(0, tk.END)
    year_entry.focus_set()

    preview_var = tk.StringVar()
    ttk.Label(dialog, textvariable=preview_var,
              font=('Arial', 9, 'italic'),
              foreground='#0055aa').grid(
        row=3, column=0, columnspan=3, padx=18, pady=(0, 8), sticky='w')

    def _update_preview(*_):
        try:
            y = int(year_var.get().strip())
            if 1900 <= y <= 2999:
                preview_var.set(f'\u2192 Year accepted: {y}')
            else:
                preview_var.set('\u26a0 Year must be between 1900 and 2999')
        except ValueError:
            preview_var.set('\u26a0 Please enter a valid 4-digit year')

    year_var.trace_add('write', _update_preview)
    _update_preview()

    today = datetime.date.today()
    quick_frame = ttk.Frame(dialog)
    quick_frame.grid(row=4, column=0, columnspan=3, padx=18, pady=(0, 8), sticky='w')
    ttk.Label(quick_frame, text='Quick select:', font=('Arial', 8)).pack(side='left', padx=(0, 6))
    for yr in [today.year - 1, today.year, today.year + 1]:
        ttk.Button(quick_frame, text=str(yr), width=6,
                   command=lambda y=yr: year_var.set(str(y))).pack(side='left', padx=2)

    def _on_ok():
        try:
            y = int(year_var.get().strip())
            if not (1900 <= y <= 2999):
                messagebox.showwarning('Invalid Year',
                    'Please enter a year between 1900 and 2999.', parent=dialog)
                return
            result['year'] = y
            dialog.destroy()
        except ValueError:
            messagebox.showwarning('Invalid Year',
                'Please enter a valid 4-digit year.', parent=dialog)

    def _on_cancel():
        dialog.destroy()

    btn_frame = ttk.Frame(dialog)
    btn_frame.grid(row=5, column=0, columnspan=3, pady=(4, 14))
    ttk.Button(btn_frame, text='OK',     command=_on_ok).pack(side='left', padx=8)
    ttk.Button(btn_frame, text='Cancel', command=_on_cancel).pack(side='left', padx=8)
    dialog.bind('<Return>', lambda e: _on_ok())
    root.wait_window(dialog)
    return result['year']

# ── EDA_AbsoluteTime formatter ───────────────────────────────────────────────
def _format_eda_absolute_time(ts_str, ts_type, recording_date=None):
    if ts_type == 'DDD':
        ddd, hh, mm, ss = _parse_ddd_timestamp(ts_str)
        date_str = recording_date.strftime('%Y-%m-%d') if recording_date else '1900-01-01'
        whole_ss = int(math.floor(ss))
        ms_val   = (ss - whole_ss) * 1000.0
        time_str = f'{hh:02d}:{mm:02d}:{whole_ss:02d}'
        ms_str   = f'{ms_val:.6f}'.rstrip('0').rstrip('.')
        return f"'{date_str} {time_str} ms {ms_str}'"
    elif ts_type == 'SECONDS':
        t        = float(ts_str.strip())
        hh, mm, ss = _seconds_since_midnight_to_hms(t)
        whole_ss = int(math.floor(ss))
        ms_val   = (ss - whole_ss) * 1000.0
        date_str = recording_date.strftime('%Y-%m-%d') if recording_date else '1900-01-01'
        time_str = f'{hh:02d}:{mm:02d}:{whole_ss:02d}'
        ms_str   = f'{ms_val:.6f}'.rstrip('0').rstrip('.')
        return f"'{date_str} {time_str} ms {ms_str}'"
    return None

# ── Timestamp auto-detection ─────────────────────────────────────────────────
def detect_absolute_timestamp(input_filepath):
    try:
        with open(input_filepath, 'r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if not header:
                return None, None, None
            first_data_row = next(reader, None)
            if not first_data_row:
                return None, None, None
            first_col_name  = header[0].strip()
            first_col_value = first_data_row[0].strip()
            ts_type = _detect_timestamp_type(first_col_value)
            return ts_type, first_col_value, first_col_name
    except Exception:
        return None, None, None

# ── DDD → datetime.date (year-aware) ────────────────────────────────────────
def _ddd_to_date(ddd_int, year):
    try:
        jan1 = datetime.date(year, 1, 1)
        return jan1 + datetime.timedelta(days=ddd_int - 1)
    except Exception:
        return datetime.date(year, 1, 1)

# ── Calendar date picker (SECONDS flow) ─────────────────────────────────────
def _ask_recording_date(root, first_ts_value):
    today  = datetime.date.today()
    result = {'date': None}
    dialog = tk.Toplevel(root)
    dialog.title('Select Recording Date')
    dialog.resizable(False, False)
    dialog.grab_set()

    view_year         = tk.IntVar(value=today.year)
    view_month        = tk.IntVar(value=today.month)
    selected_date_str = tk.StringVar(value='No date selected')
    _chosen           = {'date': None}

    ttk.Label(dialog,
              text='Seconds-since-midnight timestamp detected.',
              font=('Arial', 10, 'bold')).grid(
        row=0, column=0, columnspan=7, pady=(12, 2), padx=14, sticky='w')
    ttk.Label(dialog,
              text=(f'First value: {first_ts_value}\n'
                    f'The current year ({today.year}) is pre-selected.\n'
                    'Select the date on which this recording was made.\n'
                    'The Day-of-Year will be calculated automatically.'),
              justify='left', wraplength=380).grid(
        row=1, column=0, columnspan=7, padx=14, pady=(0, 8), sticky='w')

    nav_frame       = ttk.Frame(dialog)
    nav_frame.grid(row=2, column=0, columnspan=7, padx=14, pady=(0, 4))
    month_label_var = tk.StringVar()

    def _refresh_month_label():
        month_label_var.set(
            datetime.date(view_year.get(), view_month.get(), 1).strftime('%B %Y'))

    def _prev_month():
        y, m = view_year.get(), view_month.get()
        m -= 1
        if m < 1:
            m, y = 12, y - 1
        view_year.set(y); view_month.set(m); _build_calendar()

    def _next_month():
        y, m = view_year.get(), view_month.get()
        m += 1
        if m > 12:
            m, y = 1, y + 1
        view_year.set(y); view_month.set(m); _build_calendar()

    ttk.Button(nav_frame, text='\u2039  Prev', command=_prev_month, width=8).pack(side='left', padx=4)
    ttk.Label(nav_frame, textvariable=month_label_var,
              font=('Arial', 11, 'bold'), width=16, anchor='center').pack(side='left', padx=8)
    ttk.Button(nav_frame, text='Next  \u203a', command=_next_month, width=8).pack(side='left', padx=4)

    cal_frame    = ttk.Frame(dialog, relief='sunken', borderwidth=1)
    cal_frame.grid(row=3, column=0, columnspan=7, padx=14, pady=4)
    DAY_NAMES    = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    _day_widgets = []

    def _select_day(d):
        chosen = datetime.date(view_year.get(), view_month.get(), d)
        _chosen['date'] = chosen
        doy = chosen.timetuple().tm_yday
        selected_date_str.set(
            f"{chosen.strftime('%d %B %Y')}  \u2192  Day {doy:03d} of {chosen.year}")
        _build_calendar()

    def _build_calendar():
        nonlocal _day_widgets
        for w in _day_widgets:
            w.destroy()
        _day_widgets = []
        y, m = view_year.get(), view_month.get()
        _refresh_month_label()
        for col, name in enumerate(DAY_NAMES):
            lbl = ttk.Label(cal_frame, text=name, width=5,
                            font=('Arial', 8, 'bold'), anchor='center')
            lbl.grid(row=0, column=col, padx=1, pady=(3, 1))
            _day_widgets.append(lbl)
        first_weekday, num_days = _cal.monthrange(y, m)
        row, col = 1, first_weekday
        for day in range(1, num_days + 1):
            is_today    = (datetime.date(y, m, day) == today)
            is_selected = (_chosen['date'] == datetime.date(y, m, day))
            if is_selected:
                bg, fg, font_w = '#0078d4', '#ffffff', 'bold'
            elif is_today:
                bg, fg, font_w = '#fff3e0', '#cc6600', 'bold'
            else:
                bg, fg, font_w = dialog.cget('bg'), 'black', 'normal'
            btn = tk.Button(
                cal_frame, text=str(day), width=3,
                relief='flat', cursor='hand2',
                bg=bg, fg=fg,
                font=('Arial', 9, font_w),
                command=lambda d=day: _select_day(d))
            btn.grid(row=row, column=col, padx=1, pady=1, sticky='nsew')
            _day_widgets.append(btn)
            col += 1
            if col > 6:
                col, row = 0, row + 1

    sel_frame = ttk.Frame(dialog)
    sel_frame.grid(row=4, column=0, columnspan=7, padx=14, pady=(6, 2), sticky='w')
    ttk.Label(sel_frame, text='Selected:', font=('Arial', 9)).pack(side='left')
    ttk.Label(sel_frame, textvariable=selected_date_str,
              font=('Arial', 9, 'bold'), foreground='#0055aa').pack(side='left', padx=6)

    def _jump_to_today():
        view_year.set(today.year); view_month.set(today.month); _select_day(today.day)

    def _on_ok():
        if _chosen['date'] is None:
            messagebox.showwarning(
                'No Date Selected',
                'Please click a day on the calendar, or click Skip to use a placeholder date.',
                parent=dialog)
            return
        result['date'] = _chosen['date']
        dialog.destroy()

    def _on_skip():
        result['date'] = None
        dialog.destroy()

    btn_frame = ttk.Frame(dialog)
    btn_frame.grid(row=5, column=0, columnspan=7, pady=10)
    ttk.Button(btn_frame, text='\u2605 Today', command=_jump_to_today).pack(side='left', padx=6)
    ttk.Button(btn_frame, text='OK',           command=_on_ok).pack(side='left', padx=6)
    ttk.Button(btn_frame, text='Skip',         command=_on_skip).pack(side='left', padx=6)

    _build_calendar()
    root.wait_window(dialog)
    return result['date']

# ── Channel metadata + sampling freq GUI ─────────────────────────────────────
def get_channel_metadata_and_sampling_gui(original_csv_header,
                                           has_timestamp_col=False,
                                           suggested_hz=None,
                                           suggestion_confidence=None,
                                           suggestion_delta_s=None,
                                           suggestion_n_deltas=None):
    root   = get_main_tk_root()
    dialog = tk.Toplevel(root)
    dialog.title('Channel Metadata and Sampling Frequency Input')
    dialog.geometry('720x640')
    dialog.grab_set()

    num_columns = len(original_csv_header)
    info_text   = f'Detected {num_columns} columns.'
    if has_timestamp_col:
        info_text += '  \u2714 Absolute timestamp detected in column 1 (EDA_AbsoluteTime will be written).'
    ttk.Label(dialog, text=info_text, font=('Arial', 10, 'bold'), wraplength=700).pack(pady=5)

    canvas           = tk.Canvas(dialog)
    scrollbar        = ttk.Scrollbar(dialog, orient='vertical', command=canvas.yview)
    scrollable_frame = ttk.Frame(canvas)
    scrollable_frame.bind('<Configure>',
        lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
    canvas.create_window((0, 0), window=scrollable_frame, anchor='nw')
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side='left', fill='both', expand=True, padx=10, pady=5)
    scrollbar.pack(side='right', fill='y')

    ttk.Label(scrollable_frame, text='CHANNELNAME',
              font=('Arial', 9, 'bold')).grid(row=0, column=0, padx=5, pady=2, sticky='w')
    ttk.Label(scrollable_frame, text="UNIT (e.g. 'g')",
              font=('Arial', 9, 'bold')).grid(row=0, column=1, padx=5, pady=2, sticky='w')
    ttk.Label(scrollable_frame, text='EDA_CHANNELId',
              font=('Arial', 9, 'bold')).grid(row=0, column=2, padx=5, pady=2, sticky='w')

    entry_widgets  = []
    data_col_index = 0
    for i, col_name in enumerate(original_csv_header):
        row_num   = i + 1
        is_ts_row = (i == 0 and has_timestamp_col)
        ch_entry  = ttk.Entry(scrollable_frame, width=25)
        ch_entry.insert(0, col_name.strip())
        ch_entry.grid(row=row_num, column=0, padx=5, pady=2, sticky='ew')
        u_entry  = ttk.Entry(scrollable_frame, width=15)
        id_entry = ttk.Entry(scrollable_frame, width=10)
        if is_ts_row:
            ch_entry.config(state='disabled', foreground='grey')
            u_entry.insert(0, 'N/A')
            u_entry.config(state='disabled', foreground='grey')
            id_entry.insert(0, 'N/A')
            id_entry.config(state='disabled', foreground='grey')
        else:
            u_entry.insert(0, 'g')
            data_col_index += 1
            id_entry.insert(0, str(data_col_index))
        u_entry.grid(row=row_num, column=1, padx=5, pady=2, sticky='ew')
        id_entry.grid(row=row_num, column=2, padx=5, pady=2, sticky='ew')
        entry_widgets.append((ch_entry, u_entry, id_entry, is_ts_row))

    sampling_frame = ttk.LabelFrame(dialog, text='Sampling Frequency', padding=8)
    sampling_frame.pack(pady=8, padx=10, fill=tk.X)

    if suggested_hz is not None:
        confidence_colours = {'HIGH': '#1a7a1a', 'MEDIUM': '#8a6000', 'LOW': '#aa2200'}
        confidence_icons   = {'HIGH': '\u2714 HIGH confidence',
                               'MEDIUM': '\u26a0 MEDIUM confidence',
                               'LOW': '\u26a0 LOW confidence \u2014 please verify manually'}
        colour   = confidence_colours.get(suggestion_confidence, '#555555')
        icon_txt = confidence_icons.get(suggestion_confidence, 'Unknown confidence')
        banner   = (f'Auto-detected from {suggestion_n_deltas} inter-sample deltas:  '
                    f'{suggested_hz:,.4f} Hz  |  \u0394t\u0305 = {suggestion_delta_s:.9f} s  |  {icon_txt}')
        ttk.Label(sampling_frame, text=banner, font=('Arial', 8, 'italic'),
                  foreground=colour, wraplength=680).grid(
            row=0, column=0, columnspan=3, padx=5, pady=(0, 6), sticky='w')

    ttk.Label(sampling_frame, text='Sampling Frequency (Hz):',
              font=('Arial', 10, 'bold')).grid(row=1, column=0, padx=5, pady=2, sticky='w')
    sf_entry   = ttk.Entry(sampling_frame, width=20)
    default_sf = f'{suggested_hz:g}' if suggested_hz is not None else '51200'
    sf_entry.insert(0, default_sf)
    sf_entry.grid(row=1, column=1, padx=5, pady=2, sticky='ew')

    def _apply_suggestion():
        sf_entry.delete(0, tk.END)
        sf_entry.insert(0, f'{suggested_hz:g}')
        _update_delta()

    if suggested_hz is not None:
        ttk.Button(sampling_frame, text='\u21ba Use detected value',
                   command=_apply_suggestion).grid(row=1, column=2, padx=8, pady=2)

    ttk.Label(sampling_frame, text='You may edit this value freely. DELTA updates live.',
              font=('Arial', 8)).grid(row=2, column=0, columnspan=3, padx=5, sticky='w')
    delta_var = tk.StringVar()
    ttk.Label(sampling_frame, text='Calculated DELTA:').grid(
        row=3, column=0, padx=5, pady=2, sticky='w')
    ttk.Label(sampling_frame, textvariable=delta_var,
              font=('Arial', 9, 'bold')).grid(row=3, column=1, padx=5, pady=2, sticky='w')

    def _update_delta(*args):
        try:
            sf = float(sf_entry.get().strip())
            delta_var.set(f'{1.0/sf:.9f} seconds' if sf > 0 else 'Invalid (must be > 0)')
        except ValueError:
            delta_var.set('Invalid input')

    sf_entry.bind('<KeyRelease>', _update_delta)
    _update_delta()

    result = {'units': [], 'channel_names': [], 'channel_ids': [],
              'sampling_freq': None, 'cancelled': True}

    def on_ok():
        nonlocal result
        units, channel_names, channel_ids = [], [], []
        for ch_e, u_e, id_e, is_ts in entry_widgets:
            if is_ts:
                continue
            ch_val = ch_e.get().strip()
            u_val  = u_e.get().strip()
            id_val = id_e.get().strip()
            if not ch_val:
                messagebox.showerror('Input Error', 'CHANNELNAME cannot be empty.', parent=dialog)
                return
            if not u_val:
                messagebox.showerror('Input Error', f"UNIT for '{ch_val}' cannot be empty.", parent=dialog)
                return
            if not id_val or not id_val.isdigit():
                messagebox.showerror('Input Error',
                    f"EDA_CHANNELId for '{ch_val}' must be a non-empty number.", parent=dialog)
                return
            channel_names.append(ch_val)
            units.append(u_val)
            channel_ids.append(id_val)
        sf_str = sf_entry.get().strip()
        if not sf_str:
            messagebox.showerror('Input Error', 'Sampling Frequency cannot be empty.', parent=dialog)
            return
        try:
            sf = float(sf_str)
            if sf <= 0:
                messagebox.showerror('Input Error', 'Sampling Frequency must be positive.', parent=dialog)
                return
        except ValueError:
            messagebox.showerror('Input Error', 'Invalid Sampling Frequency.', parent=dialog)
            return
        result.update({'units': units, 'channel_names': channel_names,
                       'channel_ids': channel_ids, 'sampling_freq': sf,
                       'cancelled': False})
        dialog.destroy()

    def on_cancel():
        dialog.destroy()

    btn_frame = ttk.Frame(dialog)
    btn_frame.pack(pady=10)
    ttk.Button(btn_frame, text='OK',     command=on_ok).pack(side=tk.LEFT, padx=10)
    ttk.Button(btn_frame, text='Cancel', command=on_cancel).pack(side=tk.LEFT, padx=10)
    root.wait_window(dialog)
    if result['cancelled']:
        return None
    return {'UNIT': result['units'], 'CHANNELNAME': result['channel_names'],
            'EDA_CHANNELId': result['channel_ids'], 'SAMPLING_FREQ': result['sampling_freq']}

# ── Batch file selector ──────────────────────────────────────────────────────
def select_batch_files(root):
    """
    Show a multi-select file dialog so the user can pick one or more CSV files
    in a single operation.  Returns a list of absolute file paths (may be empty).
    """
    initial_dir = get_last_used_directory()
    if initial_dir is None:
        initial_dir = (os.path.join(os.path.expanduser('~'), 'Documents')
                       if sys.platform == 'win32' else os.path.expanduser('~'))
        if not os.path.isdir(initial_dir):
            initial_dir = os.path.expanduser('~')

    paths = filedialog.askopenfilenames(
        title='Select CSV File(s) to Convert  (hold Ctrl / Shift for multiple)',
        initialdir=initial_dir,
        filetypes=[('CSV files', '*.csv'), ('All files', '*.*')],
        parent=root)

    if paths:
        set_last_used_directory(os.path.dirname(paths[0]))
    return list(paths)

# ── Per-file metadata + timestamp resolution ─────────────────────────────────
def _resolve_file_metadata(root, input_filepath):
    """
    For a single CSV file:
      1. Detect timestamp type and first value.
      2. Estimate sample rate.
      3. Show timestamp info messagebox.
      4. Ask for recording date / year as appropriate.
      5. Show channel metadata + sampling frequency GUI.

    Returns (simcenter_header_attrs, original_csv_header, sampling_freq, ts_info)
    or None on cancellation.
    """
    try:
        with open(input_filepath, 'r', newline='', encoding='utf-8') as infile:
            reader = csv.reader(infile)
            original_csv_header = next(reader, None)
            if not original_csv_header:
                messagebox.showerror('Error',
                    f"'{os.path.basename(input_filepath)}' is empty or has no header.",
                    parent=root)
                return None
    except Exception as e:
        messagebox.showerror('Error',
            f"Could not read '{os.path.basename(input_filepath)}': {e}", parent=root)
        return None

    ts_type, first_ts_value, ts_col_name = detect_absolute_timestamp(input_filepath)
    has_timestamp_col = ts_type is not None
    suggested_hz = suggestion_conf = suggestion_delta = suggestion_n = None
    recording_date = None

    if has_timestamp_col:
        suggested_hz, suggestion_delta, suggestion_n, suggestion_conf = \
            estimate_sample_rate_from_timestamps(input_filepath, ts_type)

        ts_label = ('DDD:HH:MM:SS.sssssssss  (Dataset 1 \u2014 aircraft native system)'
                    if ts_type == 'DDD' else
                    'Seconds-since-midnight  (Dataset 2 \u2014 added instrumentation)')
        sr_line = (
            f'\n\nSample rate estimated from {suggestion_n} inter-sample deltas:\n'
            f'  \u0394t\u0305 = {suggestion_delta:.9f} s\n'
            f'  \u2192 {suggested_hz:,.4f} Hz  ({suggestion_conf} confidence)\n\n'
            'The sampling frequency field has been pre-filled \u2014 please verify.'
            if suggested_hz is not None else
            '\n\nCould not estimate sample rate. Please enter it manually.'
        )
        messagebox.showinfo(
            'Timestamp Detected',
            f'Absolute timestamp column detected!\n\n'
            f'  File    : {os.path.basename(input_filepath)}\n'
            f'  Column  : {ts_col_name}\n'
            f'  Format  : {ts_label}\n'
            f'  1st val : {first_ts_value}'
            f'{sr_line}\n\n'
            'EDA_AbsoluteTime will be added to the .asc header.',
            parent=root)

        if ts_type == 'DDD':
            global _session_ddd_year
            ddd_int, _, _, _ = _parse_ddd_timestamp(first_ts_value)
            if _session_ddd_year is not None:
                # Reuse the year confirmed for the first DDD file this batch
                chosen_year = _session_ddd_year
            else:
                provisional_date = _ddd_to_date(ddd_int, datetime.date.today().year)
                context_label    = (f'DDD:{ddd_int:03d} \u2192 '
                                    f'{provisional_date.strftime("%d %B")} '
                                    f'(Day {ddd_int:03d})')
                chosen_year = _ask_recording_year(root, context_label)
                _session_ddd_year = chosen_year   # cache for remaining DDD files
            recording_date = _ddd_to_date(ddd_int, chosen_year)

        elif ts_type == 'SECONDS':
            global _session_seconds_date
            if _session_seconds_date is not None:
                # Reuse the date (or Skip=False) confirmed for the first SECONDS file
                recording_date = _session_seconds_date if _session_seconds_date is not False else None
            else:
                recording_date = _ask_recording_date(root, first_ts_value)
                # Cache: store the date object, or False to represent "user chose Skip"
                _session_seconds_date = recording_date if recording_date is not None else False

    combined = get_channel_metadata_and_sampling_gui(
        original_csv_header, has_timestamp_col=has_timestamp_col,
        suggested_hz=suggested_hz, suggestion_confidence=suggestion_conf,
        suggestion_delta_s=suggestion_delta, suggestion_n_deltas=suggestion_n)

    if combined is None:
        return None

    sampling_freq = combined.pop('SAMPLING_FREQ')
    ts_info = {'ts_type': ts_type, 'first_ts_value': first_ts_value,
               'ts_col_name': ts_col_name, 'recording_date': recording_date}
    return combined, original_csv_header, sampling_freq, ts_info

# ── Progress widgets ─────────────────────────────────────────────────────────
def setup_progress_widgets(root, label_text, total_lines):
    global _progress_widgets
    root.deiconify()
    root.title('Conversion Progress')
    root.geometry('480x140')
    root.resizable(False, False)
    root.protocol('WM_DELETE_WINDOW', lambda: None)

    if 'file_label_var' not in _progress_widgets:
        _progress_widgets['file_label_var'] = tk.StringVar()
        _progress_widgets['file_label']     = ttk.Label(
            root, textvariable=_progress_widgets['file_label_var'],
            font=('Arial', 9, 'bold'), wraplength=460)
        _progress_widgets['file_label'].pack(pady=(10, 2), padx=10)

        _progress_widgets['label_var'] = tk.StringVar()
        _progress_widgets['label']     = ttk.Label(
            root, textvariable=_progress_widgets['label_var'], wraplength=460)
        _progress_widgets['label'].pack(pady=2, padx=10)

        _progress_widgets['bar'] = ttk.Progressbar(
            root, orient='horizontal', length=420, mode='determinate')
        _progress_widgets['bar'].pack(pady=6)

    _progress_widgets['file_label_var'].set(label_text)
    _progress_widgets['label_var'].set('Preparing...')
    _progress_widgets['bar']['value'] = 0
    root.update_idletasks()
    root.update()

def tear_down_progress_widgets(root):
    global _progress_widgets
    for key in ('file_label', 'label', 'bar'):
        if key in _progress_widgets:
            _progress_widgets[key].destroy()
    _progress_widgets = {}
    root.withdraw()
    root.title('')
    root.geometry('')

# ── Core conversion (single file) ────────────────────────────────────────────
def create_simcenter_asc_file(input_filepath, output_filepath, header_attributes,
                               sampling_freq, ts_info=None, start_time=0.0,
                               file_index=1, total_files=1):
    root = get_main_tk_root()
    try:
        delta_time = 1.0 / sampling_freq
        with open(input_filepath, 'r', newline='', encoding='utf-8') as infile:
            next(csv.reader(infile), None)
            total_lines = sum(1 for _ in infile)

        file_banner = (f'Converting file {file_index} of {total_files}: '
                       f'{os.path.basename(input_filepath)}')
        setup_progress_widgets(root, file_banner, total_lines)

        ts_type        = ts_info.get('ts_type')        if ts_info else None
        recording_date = ts_info.get('recording_date') if ts_info else None
        eda_abs_time_line = None
        if ts_type in ('DDD', 'SECONDS'):
            first_ts = ts_info.get('first_ts_value', '')
            eda_str  = _format_eda_absolute_time(first_ts, ts_type, recording_date)
            if eda_str:
                eda_abs_time_line = f'EDA_AbsoluteTime = [{eda_str}]'

        header_lines = [
            'BEGIN',
            '#  Start of X axis in seconds',
            f'START  = {start_time}',
            '#  Time step in Seconds',
            f'DELTA   = {delta_time}',
        ]
        if eda_abs_time_line:
            header_lines.append('#  Absolute start time (auto-detected from timestamp column)')
            header_lines.append(eda_abs_time_line)
        header_lines += [
            '#  Y axis unit label',
            f"UNIT = {header_attributes['UNIT']}",
            '#  Channel Name or Point ID',
            f"CHANNELNAME = {header_attributes['CHANNELNAME']}",
            '#  CHANNEL NUMBER',
            f"EDA_CHANNELId = {header_attributes['EDA_CHANNELId']}",
            'END\n'
        ]
        simcenter_header = '\n'.join(header_lines)
        update_interval  = max(1, total_lines // 100)

        with open(input_filepath, 'r', newline='', encoding='utf-8') as infile, \
             open(output_filepath, 'w', newline='', encoding='utf-8') as outfile:
            outfile.write(simcenter_header)
            reader = csv.reader(infile)
            next(reader, None)
            rows_written = 0
            for row in reader:
                data_row = row[1:] if ts_type in ('DDD', 'SECONDS') and len(row) > 1 else row
                outfile.write(','.join(data_row) + '\n')
                rows_written += 1
                if rows_written % update_interval == 0 or rows_written == total_lines:
                    pct = (rows_written / total_lines * 100) if total_lines > 0 else 100
                    _progress_widgets['bar']['value'] = pct
                    _progress_widgets['label_var'].set(
                        f'{rows_written}/{total_lines} rows \u2013 {pct:.1f}%')
                    root.update_idletasks()
                    root.update()

        _progress_widgets['bar']['value'] = 100
        _progress_widgets['label_var'].set(
            f'{total_lines}/{total_lines} rows \u2013 100.0%  \u2714 Done')
        root.update_idletasks()
        root.update()

        abs_note = (f'\nEDA_AbsoluteTime: {eda_abs_time_line}'
                    if eda_abs_time_line
                    else '\nNo absolute timestamp \u2013 EDA_AbsoluteTime not written.')
        return True, rows_written, abs_note

    except FileNotFoundError:
        messagebox.showerror('Error',
            f"Input file '{input_filepath}' not found.", parent=root)
        return False, 0, ''
    except Exception as e:
        messagebox.showerror('Error',
            f"Unexpected error converting '{os.path.basename(input_filepath)}': {e}",
            parent=root)
        return False, 0, ''

# ── Batch summary dialog ─────────────────────────────────────────────────────
def _show_batch_summary(root, results):
    """
    Display a scrollable summary of all files converted in the batch.
    results = list of dicts:
        {'input': str, 'output': str, 'rows': int, 'abs_note': str, 'ok': bool}
    """
    dialog = tk.Toplevel(root)
    dialog.title('Batch Conversion \u2014 Summary')
    dialog.geometry('700x420')
    dialog.grab_set()

    n_ok  = sum(1 for r in results if r['ok'])
    n_err = len(results) - n_ok

    ttk.Label(dialog,
              text=f'Batch complete:  {n_ok} succeeded,  {n_err} failed.',
              font=('Arial', 11, 'bold')).pack(pady=(12, 4), padx=14, anchor='w')

    frame  = ttk.Frame(dialog)
    frame.pack(fill='both', expand=True, padx=14, pady=4)
    text   = tk.Text(frame, wrap='word', font=('Courier', 9), state='normal',
                     relief='sunken', borderwidth=1)
    vsb    = ttk.Scrollbar(frame, orient='vertical', command=text.yview)
    text.configure(yscrollcommand=vsb.set)
    vsb.pack(side='right', fill='y')
    text.pack(side='left', fill='both', expand=True)

    for i, r in enumerate(results, 1):
        status = '\u2714 OK ' if r['ok'] else '\u2718 ERR'
        text.insert('end', f"[{i:02d}] {status}  {os.path.basename(r['input'])}\n")
        if r['ok']:
            text.insert('end', f"       \u2192 {r['output']}\n")
            text.insert('end', f"       Rows: {r['rows']}{r['abs_note']}\n\n")
        else:
            text.insert('end', f"       Conversion failed \u2014 see earlier error dialog.\n\n")

    text.configure(state='disabled')

    ttk.Button(dialog, text='Close', command=dialog.destroy).pack(pady=10)
    root.wait_window(dialog)

# ── Session date/year cache helpers ──────────────────────────────────────────

def _reset_session_date_cache():
    """Reset per-batch date/year cache so each new batch starts fresh."""
    global _session_ddd_year, _session_seconds_date
    _session_ddd_year     = None
    _session_seconds_date = None

# ── Main batch loop ──────────────────────────────────────────────────────────
def main_conversion_process_gui():
    root = get_main_tk_root()

    while True:
        # ── Step 1: select one or more CSV files ──────────────────────────
        input_files = select_batch_files(root)
        if not input_files:
            messagebox.showinfo('Cancelled', 'No files selected. Exiting.', parent=root)
            break

        total_files = len(input_files)

        # Reset the date/year cache so each new batch prompts the user afresh
        _reset_session_date_cache()

        # ── Step 2: collect metadata for every file before converting ─────
        file_jobs = []   # list of (input_path, output_path, attrs, sf, ts_info)

        for idx, input_csv_file in enumerate(input_files, 1):
            fname = os.path.basename(input_csv_file)

            # Banner so user knows which file they are configuring
            messagebox.showinfo(
                f'File {idx} of {total_files}',
                f'Now configuring:\n\n  {fname}\n\n'
                f'({idx} of {total_files} files selected)',
                parent=root)

            meta = _resolve_file_metadata(root, input_csv_file)
            if meta is None:
                # User cancelled metadata for this file — ask whether to skip or abort
                choice = messagebox.askyesno(
                    'Skip File?',
                    f"Configuration was cancelled for:\n  {fname}\n\n"
                    f"Skip this file and continue with the remaining {total_files - idx}?",
                    parent=root)
                if not choice:
                    break   # abort entire batch
                continue    # skip this file

            simcenter_header_attrs, original_csv_header, sampling_freq, ts_info = meta

            # Output file path
            input_dir = os.path.dirname(input_csv_file)
            base_name = os.path.splitext(os.path.basename(input_csv_file))[0]
            output_asc_file = filedialog.asksaveasfilename(
                title=f'Save Output for: {fname}',
                initialdir=input_dir,
                initialfile=f'{base_name}.asc',
                defaultextension='.asc',
                filetypes=[('Simcenter Testlab ASC files', '*.asc'), ('All files', '*.*')],
                parent=root)

            if not output_asc_file:
                choice = messagebox.askyesno(
                    'Skip File?',
                    f"No output path chosen for:\n  {fname}\n\n"
                    f"Skip this file and continue?",
                    parent=root)
                if not choice:
                    break
                continue

            output_dir = os.path.dirname(output_asc_file)
            try:
                if not os.path.exists(output_dir):
                    os.makedirs(output_dir)
            except OSError as e:
                messagebox.showerror('Error',
                    f"Cannot create directory '{output_dir}': {e}", parent=root)
                continue

            file_jobs.append((input_csv_file, output_asc_file,
                              simcenter_header_attrs, sampling_freq, ts_info))

        if not file_jobs:
            messagebox.showinfo('Nothing to Convert',
                'No files were queued for conversion.', parent=root)
            break

        # ── Step 3: convert all queued files ──────────────────────────────
        batch_results = []
        for job_idx, (in_path, out_path, attrs, sf, ts_info) in enumerate(file_jobs, 1):
            ok, rows, abs_note = create_simcenter_asc_file(
                in_path, out_path, attrs, sf,
                ts_info=ts_info,
                file_index=job_idx,
                total_files=len(file_jobs))
            batch_results.append({
                'input':    in_path,
                'output':   out_path,
                'rows':     rows,
                'abs_note': abs_note,
                'ok':       ok})

        tear_down_progress_widgets(root)

        # ── Step 4: show summary and ask whether to run another batch ─────
        _show_batch_summary(root, batch_results)

        again = messagebox.askyesno(
            'Convert Another Batch?',
            'Would you like to select more files for another batch conversion?',
            default=messagebox.NO,
            parent=root)
        if not again:
            break

    root.destroy()
    sys.exit()

if __name__ == '__main__':
    main_conversion_process_gui()

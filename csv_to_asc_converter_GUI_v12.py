#!/usr/bin/env python3
"""
csv_to_asc_converter_GUI_v12.py
Converts CSV / XLSX files to Simcenter Testlab ASC format.

Changes vs v11
==============
FIX 4 - Single ASC header block (was one per channel)
    The BEGIN...END header is now written ONCE per file.
    All channel names, units and IDs are written as
    space-separated lists on a single line each, e.g.:
        UNIT = g g m/s
        CHANNELNAME = ch1 ch2 ch3
        EDA_CHANNELId = 1 2 3

FIX 5 - XLSX sample-and-hold (forward-fill)
    Empty XLSX cells are filled with the last non-empty
    value in that column. CSV files are unchanged.

FIX 6 - Repeat-batch prompt always shown
    "Convert another batch?" appears after every run,
    for both CSV and XLSX, single file or batch.

FIX 7 - XLSX conversion summary
    Done messagebox lists every file (OK / FAIL) for
    both CSV and XLSX, matching existing CSV behaviour.
"""

import calendar as _cal
import csv
import datetime
import os
import re
import sys
sys.stdout.reconfigure(encoding='utf-8')
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    import openpyxl as _openpyxl
    _OPENPYXL_AVAILABLE = True
except ImportError:
    _OPENPYXL_AVAILABLE = False

_main_tk_root     = None
_progress_widgets = {}
LAST_DIR_FILE = os.path.join(os.path.expanduser('~'),
                             '.simcenter_csv_converter_last_dir.txt')
_TS_SAMPLE_ROWS   = 10
_session_ddd_year     = None
_session_seconds_date = None


# ---------------------------------------------------------------------------
# Tkinter root
# ---------------------------------------------------------------------------

def get_main_tk_root():
    global _main_tk_root
    if _main_tk_root is None or not _main_tk_root.winfo_exists():
        _main_tk_root = tk.Tk()
        _main_tk_root.withdraw()
    return _main_tk_root


# ---------------------------------------------------------------------------
# Last-directory persistence
# ---------------------------------------------------------------------------

def _load_last_dir():
    try:
        with open(LAST_DIR_FILE, 'r', encoding='utf-8') as f:
            d = f.read().strip()
        return d if os.path.isdir(d) else None
    except Exception:
        return None

def _save_last_dir(path):
    try:
        with open(LAST_DIR_FILE, 'w', encoding='utf-8') as f:
            f.write(path)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# XLSX helpers
# ---------------------------------------------------------------------------

def _is_xlsx(filepath):
    return filepath.lower().endswith('.xlsx')

def _read_xlsx_non_comment_rows(filepath):
    """Return (non_comment_rows, all_rows)."""
    if not _OPENPYXL_AVAILABLE:
        raise RuntimeError(
            "openpyxl is required to read .xlsx files. "
            "Install with:  pip install openpyxl")
    wb = _openpyxl.load_workbook(filepath, read_only=True, data_only=True)
    ws = wb.active
    all_rows = [list(r) for r in ws.iter_rows(values_only=True)]
    wb.close()
    non_comment = []
    for row in all_rows:
        first = str(row[0]).strip() if row[0] is not None else ''
        if not first.startswith('#'):
            non_comment.append(row)
    return non_comment, all_rows


# ---------------------------------------------------------------------------
# Timestamp detection
# ---------------------------------------------------------------------------

_DDD_RE = re.compile(r'^\d{3}:\d{2}:\d{2}:\d{2}(?:\.\d+)?$')

def detect_absolute_timestamp(filepath):
    """Return (ts_type, first_ts_value, ts_col_name) or (None,None,None)."""
    try:
        if _is_xlsx(filepath):
            non_comment, _ = _read_xlsx_non_comment_rows(filepath)
            if len(non_comment) < 4:
                return None, None, None
            ts_col_name = str(non_comment[0][0]).strip() if non_comment[0][0] is not None else ''
            first_val   = str(non_comment[3][0]).strip() if non_comment[3][0] is not None else ''
        else:
            with open(filepath, 'r', newline='', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                if not header:
                    return None, None, None
                ts_col_name = header[0].strip()
                first_val = ''
                for row in reader:
                    if row and row[0].strip():
                        first_val = row[0].strip()
                        break
        if _DDD_RE.match(first_val):
            return 'DDD', first_val, ts_col_name
        try:
            fv = float(first_val)
            if 0 <= fv <= 86400:
                return 'SECONDS', first_val, ts_col_name
        except ValueError:
            pass
        return None, None, None
    except Exception:
        return None, None, None


# ---------------------------------------------------------------------------
# Sample-rate estimation
# ---------------------------------------------------------------------------

def _parse_ddd_timestamp(ts_str):
    parts = str(ts_str).strip().split(':')
    return int(parts[0]), int(parts[1]), int(parts[2]), float(parts[3])

def _ddd_to_seconds_of_day(ts_str):
    _, hh, mm, ss = _parse_ddd_timestamp(ts_str)
    return hh * 3600.0 + mm * 60.0 + ss

def estimate_sample_rate(filepath, ts_type):
    """Return (hz, conf, delta_s, n_deltas) or (None,None,None,None)."""
    try:
        timestamps = []
        if _is_xlsx(filepath):
            non_comment, _ = _read_xlsx_non_comment_rows(filepath)
            data_rows = non_comment[3:]
            for row in data_rows[:_TS_SAMPLE_ROWS + 1]:
                raw = str(row[0]).strip() if row[0] is not None else ''
                if raw:
                    timestamps.append(raw)
        else:
            with open(filepath, 'r', newline='', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader, None)
                for row in reader:
                    if row and row[0].strip():
                        timestamps.append(row[0].strip())
                    if len(timestamps) > _TS_SAMPLE_ROWS:
                        break
        if len(timestamps) < 2:
            return None, None, None, None
        secs = ([_ddd_to_seconds_of_day(t) for t in timestamps] if ts_type == 'DDD'
                else [float(t) for t in timestamps])
        deltas = [abs(secs[i+1] - secs[i]) for i in range(len(secs) - 1)]
        deltas = [d for d in deltas if d > 0]
        if not deltas:
            return None, None, None, None
        avg_delta = sum(deltas) / len(deltas)
        hz        = 1.0 / avg_delta
        spread    = max(deltas) - min(deltas)
        conf = ('HIGH'   if spread < avg_delta * 0.01 else
                'MEDIUM' if spread < avg_delta * 0.10 else 'LOW')
        return hz, conf, avg_delta, len(deltas)
    except Exception:
        return None, None, None, None


# ---------------------------------------------------------------------------
# Date / year helpers
# ---------------------------------------------------------------------------

def _ddd_to_date(ddd_int, year):
    return datetime.date(year, 1, 1) + datetime.timedelta(days=ddd_int - 1)

def _ask_recording_year(root, context_label):
    global _session_ddd_year
    if _session_ddd_year is not None:
        return _session_ddd_year
    result = {'year': datetime.date.today().year}
    dlg = tk.Toplevel(root)
    dlg.title('Recording Year')
    dlg.grab_set()
    ttk.Label(dlg, text=f'Timestamp context: {context_label}',
              font=('Arial', 10)).pack(pady=(12, 4), padx=16)
    ttk.Label(dlg, text='Recording year:',
              font=('Arial', 10)).pack(pady=(4, 0), padx=16)
    year_var = tk.StringVar(value=str(result['year']))
    ttk.Entry(dlg, textvariable=year_var, width=8, font=('Arial', 12)).pack(pady=4)
    btn_frame = ttk.Frame(dlg)
    btn_frame.pack(pady=6)
    cur_y = datetime.date.today().year
    for y in [cur_y - 1, cur_y, cur_y + 1]:
        ttk.Button(btn_frame, text=str(y),
                   command=lambda _y=y: year_var.set(str(_y))).pack(side=tk.LEFT, padx=4)
    def on_ok():
        try:
            result['year'] = int(year_var.get().strip())
            dlg.destroy()
        except ValueError:
            messagebox.showerror('Invalid year', 'Please enter a 4-digit year.', parent=dlg)
    ttk.Button(dlg, text='OK', command=on_ok).pack(pady=8)
    root.wait_window(dlg)
    _session_ddd_year = result['year']
    return result['year']

def _ask_recording_date(root, first_ts_value):
    global _session_seconds_date
    if _session_seconds_date is not None:
        return _session_seconds_date if _session_seconds_date is not False else None
    today  = datetime.date.today()
    result = {'date': today}
    dlg    = tk.Toplevel(root)
    dlg.title('Recording Date')
    dlg.grab_set()
    ttk.Label(dlg, text=f'First timestamp (seconds since midnight): {first_ts_value}',
              font=('Arial', 10)).pack(pady=(12, 4), padx=16)
    ttk.Label(dlg, text=f'The current year ({today.year}) is pre-selected.',
              font=('Arial', 9, 'italic')).pack(pady=(0, 6), padx=16)
    cal_frame  = ttk.Frame(dlg)
    cal_frame.pack(padx=16, pady=4)
    nav_year   = tk.IntVar(value=today.year)
    nav_month  = tk.IntVar(value=today.month)
    sel_day    = tk.IntVar(value=today.day)
    status_var = tk.StringVar()
    day_frame  = ttk.Frame(cal_frame)
    def _refresh_calendar():
        for w in day_frame.winfo_children():
            w.destroy()
        y, m = nav_year.get(), nav_month.get()
        for c, dn in enumerate(['Mo','Tu','We','Th','Fr','Sa','Su']):
            ttk.Label(day_frame, text=dn, width=4, font=('Arial', 8, 'bold')).grid(row=0, column=c)
        for r, week in enumerate(_cal.monthcalendar(y, m)):
            for c, day in enumerate(week):
                if day == 0:
                    ttk.Label(day_frame, text='', width=4).grid(row=r+1, column=c)
                else:
                    tk.Button(day_frame, text=str(day), width=3, relief='flat',
                              command=lambda d=day: _select_day(d)).grid(
                                  row=r+1, column=c, padx=1, pady=1)
        _update_status()
    def _select_day(d):
        sel_day.set(d)
        _update_status()
    def _update_status():
        try:
            d   = datetime.date(nav_year.get(), nav_month.get(), sel_day.get())
            doy = d.timetuple().tm_yday
            status_var.set(f'{d.strftime("%d %B %Y")}  ->  Day {doy:03d} of {d.year}')
            result['date'] = d
        except ValueError:
            status_var.set('(invalid date)')
    hdr = ttk.Frame(cal_frame)
    hdr.pack()
    month_lbl = ttk.Label(hdr,
                          text=f'{_cal.month_name[today.month]} {today.year}',
                          width=14, anchor='center')
    def _prev_month():
        y, m = nav_year.get(), nav_month.get()
        m -= 1
        if m < 1:
            m, y = 12, y - 1
        nav_year.set(y); nav_month.set(m)
        month_lbl.config(text=f'{_cal.month_name[m]} {y}')
        _refresh_calendar()
    def _next_month():
        y, m = nav_year.get(), nav_month.get()
        m += 1
        if m > 12:
            m, y = 1, y + 1
        nav_year.set(y); nav_month.set(m)
        month_lbl.config(text=f'{_cal.month_name[m]} {y}')
        _refresh_calendar()
    ttk.Button(hdr, text='<', width=2, command=_prev_month).pack(side=tk.LEFT)
    month_lbl.pack(side=tk.LEFT)
    ttk.Button(hdr, text='>', width=2, command=_next_month).pack(side=tk.LEFT)
    day_frame.pack(pady=4)
    _refresh_calendar()
    ttk.Label(dlg, textvariable=status_var, font=('Arial', 9, 'italic')).pack(pady=4)
    def on_ok():
        dlg.destroy()
    def on_skip():
        result['date'] = None
        dlg.destroy()
    bf = ttk.Frame(dlg)
    bf.pack(pady=8)
    ttk.Button(bf, text='OK',   command=on_ok).pack(side=tk.LEFT, padx=6)
    ttk.Button(bf, text='Today',
               command=lambda: (_select_day(today.day),
                                nav_year.set(today.year),
                                nav_month.set(today.month),
                                _refresh_calendar())).pack(side=tk.LEFT, padx=6)
    ttk.Button(bf, text='Skip', command=on_skip).pack(side=tk.LEFT, padx=6)
    root.wait_window(dlg)
    chosen = result['date']
    _session_seconds_date = chosen if chosen is not None else False
    return chosen


# ---------------------------------------------------------------------------
# Progress bar
# ---------------------------------------------------------------------------

def _setup_progress_bar(root):
    global _progress_widgets
    if _progress_widgets:
        return
    pf  = ttk.LabelFrame(root, text='Conversion Progress', padding=8)
    pf.pack(padx=16, pady=8, fill=tk.X)
    bar = ttk.Progressbar(pf, orient='horizontal', length=400, mode='determinate')
    bar.pack(fill=tk.X, pady=4)
    lv  = tk.StringVar(value='Waiting...')
    ttk.Label(pf, textvariable=lv, font=('Arial', 9)).pack()
    _progress_widgets = {'bar': bar, 'label_var': lv}
    root.deiconify()
    root.update()


# ---------------------------------------------------------------------------
# Channel metadata GUI
# ---------------------------------------------------------------------------

def get_channel_metadata_and_sampling_gui(original_csv_header,
                                          has_timestamp_col=False,
                                          suggested_hz=None,
                                          suggestion_confidence=None,
                                          suggestion_delta_s=None,
                                          suggestion_n_deltas=None,
                                          prefill_units=None):
    root   = get_main_tk_root()
    dialog = tk.Toplevel(root)
    dialog.title('Channel Metadata and Sampling Frequency Input')
    dialog.geometry('720x640')
    dialog.grab_set()
    num_columns = len(original_csv_header)
    info_text   = f'Detected {num_columns} columns.'
    if has_timestamp_col:
        info_text += ('  ✔ Absolute timestamp detected in column 1 '
                      '(EDA_AbsoluteTime will be written).')
    ttk.Label(dialog, text=info_text,
              font=('Arial', 10, 'bold'), wraplength=700).pack(pady=5)
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
            unit_default = 'g'
            if prefill_units and i < len(prefill_units):
                raw_unit = str(prefill_units[i]).strip().strip('()')
                if raw_unit and raw_unit.lower() not in ('n/a', 'none', ''):
                    unit_default = raw_unit
            u_entry.insert(0, unit_default)
            data_col_index += 1
            id_entry.insert(0, str(data_col_index))
        u_entry.grid(row=row_num, column=1, padx=5, pady=2, sticky='ew')
        id_entry.grid(row=row_num, column=2, padx=5, pady=2, sticky='ew')
        entry_widgets.append((ch_entry, u_entry, id_entry, is_ts_row))
    sampling_frame = ttk.LabelFrame(dialog, text='Sampling Frequency', padding=8)
    sampling_frame.pack(pady=8, padx=10, fill=tk.X)
    if suggested_hz is not None:
        hint = (f'Suggested: {suggested_hz:.4f} Hz  '
                f'[confidence: {suggestion_confidence}, '
                f'dt={suggestion_delta_s:.6f} s, '
                f'n={suggestion_n_deltas} deltas]')
        ttk.Label(sampling_frame, text=hint,
                  font=('Arial', 9, 'italic'), foreground='blue').pack(anchor='w')
    sf_frame = ttk.Frame(sampling_frame)
    sf_frame.pack(anchor='w')
    ttk.Label(sf_frame, text='Sampling Frequency (Hz):').pack(side=tk.LEFT)
    sf_entry = ttk.Entry(sf_frame, width=12)
    sf_entry.pack(side=tk.LEFT, padx=6)
    if suggested_hz is not None:
        sf_entry.insert(0, f'{suggested_hz:.4f}')
    result = {'cancelled': True}
    def on_ok():
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
            messagebox.showerror('Input Error', 'Sampling Frequency must be a number.', parent=dialog)
            return
        result.update({'cancelled': False, 'units': units,
                       'channel_names': channel_names,
                       'channel_ids': channel_ids,
                       'sampling_freq': sf})
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
            'EDA_CHANNELId': result['channel_ids'],
            'SAMPLING_FREQ': result['sampling_freq']}


# ---------------------------------------------------------------------------
# Per-file metadata resolution
# ---------------------------------------------------------------------------

def _resolve_file_metadata(root, input_filepath):
    """Return (attrs, header, sampling_freq, ts_info) or None."""
    try:
        if _is_xlsx(input_filepath):
            non_comment, _ = _read_xlsx_non_comment_rows(input_filepath)
            if len(non_comment) < 4:
                messagebox.showerror('Error',
                    f"'{os.path.basename(input_filepath)}' has fewer than 4 "
                    "non-comment rows (need: names, descriptions, units, data).",
                    parent=root)
                return None
            original_csv_header = [str(c).strip() if c is not None else ''
                                    for c in non_comment[0]]
            prefill_units       = [str(c).strip() if c is not None else ''
                                    for c in non_comment[2]]
        else:
            prefill_units = None
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
        suggested_hz, suggestion_conf, suggestion_delta, suggestion_n = \
            estimate_sample_rate(input_filepath, ts_type)
        ts_label = {'DDD': 'DDD (Day:HH:MM:SS)', 'SECONDS': 'Seconds since midnight'}
        msg = (f"Timestamp column detected: '{ts_col_name}'\n"
               f"Format: {ts_label.get(ts_type, ts_type)}\n"
               f"First value: {first_ts_value}")
        if suggested_hz:
            msg += (f"\nEstimated sample rate: {suggested_hz:.4f} Hz "
                    f"({suggestion_conf} confidence)")
        messagebox.showinfo('Timestamp Detected', msg, parent=root)
    global _session_ddd_year, _session_seconds_date
    if ts_type == 'DDD':
        ddd_int, _, _, _ = _parse_ddd_timestamp(first_ts_value)
        provisional_date = _ddd_to_date(ddd_int, datetime.date.today().year)
        context_label    = (f'DDD:{ddd_int:03d} -> '
                            f'{provisional_date.strftime("%d %B")} '
                            f'(Day {ddd_int:03d})')
        chosen_year    = _ask_recording_year(root, context_label)
        recording_date = _ddd_to_date(ddd_int, chosen_year)
    elif ts_type == 'SECONDS':
        if _session_seconds_date is not None:
            recording_date = (_session_seconds_date
                              if _session_seconds_date is not False else None)
        else:
            recording_date = _ask_recording_date(root, first_ts_value)
            _session_seconds_date = recording_date if recording_date is not None else False
    combined = get_channel_metadata_and_sampling_gui(
        original_csv_header,
        has_timestamp_col=has_timestamp_col,
        suggested_hz=suggested_hz,
        suggestion_confidence=suggestion_conf,
        suggestion_delta_s=suggestion_delta,
        suggestion_n_deltas=suggestion_n,
        prefill_units=prefill_units)
    if combined is None:
        return None
    sampling_freq = combined.pop('SAMPLING_FREQ')
    ts_info = {'ts_type': ts_type, 'first_ts_value': first_ts_value,
               'ts_col_name': ts_col_name, 'recording_date': recording_date}
    return combined, original_csv_header, sampling_freq, ts_info


# ---------------------------------------------------------------------------
# ASC header builder -- FIX 4: single block for all channels
# ---------------------------------------------------------------------------

def _build_eda_abs_time_line(ts_type, first_ts_value, recording_date):
    try:
        if ts_type == 'DDD':
            _, hh, mm, ss_frac = _parse_ddd_timestamp(first_ts_value)
            ss_int = int(ss_frac)
            ms_val = (ss_frac - ss_int) * 1000.0
            date_pfx = recording_date.strftime('%Y-%m-%d ') if recording_date else ''
            return f'EDA_AbsoluteTime = {date_pfx}{hh:02d}:{mm:02d}:{ss_int:02d} ms {ms_val:.6f}'
        elif ts_type == 'SECONDS':
            total_s = float(first_ts_value)
            hh      = int(total_s // 3600)
            mm      = int((total_s % 3600) // 60)
            ss      = total_s % 60
            ss_int  = int(ss)
            ms_val  = (ss - ss_int) * 1000.0
            date_pfx = recording_date.strftime('%Y-%m-%d ') if recording_date else ''
            return f'EDA_AbsoluteTime = {date_pfx}{hh:02d}:{mm:02d}:{ss_int:02d} ms {ms_val:.6f}'
    except Exception:
        pass
    return None

def _build_asc_header(header_attributes, sampling_freq, ts_info):
    """Build ONE BEGIN...END block listing all channels."""
    ts_type        = ts_info.get('ts_type')
    first_ts_value = ts_info.get('first_ts_value')
    recording_date = ts_info.get('recording_date')
    delta_time     = 1.0 / sampling_freq if sampling_freq else 0.0
    unit_str = ' '.join(header_attributes['UNIT'])
    name_str = ' '.join(header_attributes['CHANNELNAME'])
    id_str   = ' '.join(header_attributes['EDA_CHANNELId'])
    eda_abs_time_line = None
    if ts_type and first_ts_value:
        eda_abs_time_line = _build_eda_abs_time_line(ts_type, first_ts_value, recording_date)
    lines = [
        'BEGIN',
        '#  Start of X axis in seconds',
        'START  = 0.0',
        '#  Time step in Seconds',
        f'DELTA   = {delta_time}',
    ]
    if eda_abs_time_line:
        lines.append('#  Absolute start time (auto-detected from timestamp column)')
        lines.append(eda_abs_time_line)
    lines += [
        '#  Y axis unit label',
        f'UNIT = {unit_str}',
        '#  Channel Name or Point ID',
        f'CHANNELNAME = {name_str}',
        '#  CHANNEL NUMBER',
        f'EDA_CHANNELId = {id_str}',
        'END\n'
    ]
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Row counting
# ---------------------------------------------------------------------------

def _count_data_lines(filepath, ts_type):
    try:
        if _is_xlsx(filepath):
            non_comment, _ = _read_xlsx_non_comment_rows(filepath)
            return max(0, len(non_comment) - 3)
        else:
            with open(filepath, 'r', newline='', encoding='utf-8') as f:
                return max(0, sum(1 for _ in f) - 1)
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Data writer -- FIX 5: XLSX sample-and-hold
# ---------------------------------------------------------------------------

def _write_data_rows(input_filepath, output_filepath, simcenter_header,
                     ts_type, total_lines, root):
    update_interval = max(1, total_lines // 100)
    rows_written    = 0
    def _tick():
        nonlocal rows_written
        rows_written += 1
        if rows_written % update_interval == 0 or rows_written == total_lines:
            pct = (rows_written / total_lines * 100) if total_lines > 0 else 100
            _progress_widgets['bar']['value'] = pct
            _progress_widgets['label_var'].set(
                f'{rows_written}/{total_lines} rows - {pct:.1f}%')
            root.update_idletasks()
            root.update()
    if _is_xlsx(input_filepath):
        non_comment, _ = _read_xlsx_non_comment_rows(input_filepath)
        data_rows   = non_comment[3:]
        col_start   = 1 if ts_type in ('DDD', 'SECONDS') else 0
        n_data_cols = len(data_rows[0]) - col_start if data_rows else 0
        last_vals   = [None] * n_data_cols
        with open(output_filepath, 'w', newline='', encoding='utf-8') as outfile:
            outfile.write(simcenter_header)
            for row in data_rows:
                data_cols = list(row[col_start:])
                for ci in range(len(data_cols)):
                    if data_cols[ci] is not None and str(data_cols[ci]).strip() != '':
                        last_vals[ci] = data_cols[ci]
                    else:
                        data_cols[ci] = last_vals[ci]
                outfile.write(','.join(
                    str(c) if c is not None else '' for c in data_cols) + '\n')
                _tick()
    else:
        with open(input_filepath, 'r', newline='', encoding='utf-8') as infile, \
             open(output_filepath, 'w', newline='', encoding='utf-8') as outfile:
            outfile.write(simcenter_header)
            reader = csv.reader(infile)
            next(reader, None)
            for row in reader:
                data_row = row[1:] if ts_type in ('DDD', 'SECONDS') and len(row) > 1 else row
                outfile.write(','.join(data_row) + '\n')
                _tick()
    _progress_widgets['bar']['value'] = 100
    _progress_widgets['label_var'].set(
        f'{total_lines}/{total_lines} rows - 100.0%  Done')
    root.update_idletasks()
    root.update()


# ---------------------------------------------------------------------------
# Batch conversion -- FIX 6+7
# ---------------------------------------------------------------------------

def convert_files(input_files):
    global _session_ddd_year, _session_seconds_date
    _session_ddd_year     = None
    _session_seconds_date = None
    root = get_main_tk_root()
    _setup_progress_bar(root)
    total_files   = len(input_files)
    converted_ok  = []
    converted_err = []
    for idx, input_csv_file in enumerate(input_files):
        fname = os.path.basename(input_csv_file)
        _progress_widgets['label_var'].set(f'File {idx + 1}/{total_files}: {fname}')
        root.update_idletasks()
        root.update()
        meta = _resolve_file_metadata(root, input_csv_file)
        if meta is None:
            remaining = total_files - idx - 1
            if remaining > 0:
                choice = messagebox.askyesno('Skip File?',
                    f"Configuration was cancelled for:\n  {fname}\n\n"
                    f"Skip this file and continue with the remaining {remaining}?",
                    parent=root)
                if not choice:
                    break
            continue
        simcenter_header_attrs, original_csv_header, sampling_freq, ts_info = meta
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
            converted_err.append((fname, 'Output path not chosen'))
            continue
        ts_type     = ts_info['ts_type']
        total_lines = _count_data_lines(input_csv_file, ts_type)
        asc_header  = _build_asc_header(simcenter_header_attrs, sampling_freq, ts_info)
        try:
            _write_data_rows(input_csv_file, output_asc_file,
                             asc_header, ts_type, total_lines, root)
            converted_ok.append((fname, output_asc_file))
        except Exception as e:
            converted_err.append((fname, str(e)))
    summary = [f'Conversion complete.  {len(converted_ok)} succeeded, '
               f'{len(converted_err)} failed.\n']
    for fn, out in converted_ok:
        summary.append(f'  OK    {fn}  ->  {out}')
    for fn, err in converted_err:
        summary.append(f'  FAIL  {fn}  ({err})')
    messagebox.showinfo('Done', '\n'.join(summary), parent=root)


# ---------------------------------------------------------------------------
# Entry point -- FIX 6: repeat prompt always shown
# ---------------------------------------------------------------------------

def main():
    global _progress_widgets
    root     = get_main_tk_root()
    last_dir = _load_last_dir()
    while True:
        _progress_widgets = {}
        input_files = filedialog.askopenfilenames(
            title='Select CSV / XLSX file(s) to convert',
            initialdir=last_dir or os.path.expanduser('~'),
            filetypes=[
                ('Supported files', '*.csv *.xlsx'),
                ('CSV files',       '*.csv'),
                ('Excel files',     '*.xlsx'),
                ('All files',       '*.*'),
            ],
            parent=root)
        if not input_files:
            break
        _save_last_dir(os.path.dirname(input_files[0]))
        convert_files(list(input_files))
        again = messagebox.askyesno(
            'Convert Another Batch?',
            'Would you like to select another batch of files to convert?',
            parent=root)
        if not again:
            break
    try:
        root.destroy()
    except Exception:
        pass


if __name__ == '__main__':
    main()

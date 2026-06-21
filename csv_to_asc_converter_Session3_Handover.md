# CSV to ASC Converter — Development Handover Document (Session 3)

Document Date: 20 June 2026  
Project: Python-based CSV to Simcenter Testlab ASC Converter — Continued Enhancement  
Primary Contact: Myles  
AI Assistant: SiemensGPT  

---

## 1. Overview

This document records all user inputs, requirements, and code changes made during the
third development session for the `csv_to_asc_converter_GUI.py` Python script. It is
intended to complement the earlier handover documents (Session 1 dated 24 April 2026;
Session 2 dated 20 June 2026) and serves as a complete reference for the changes
incorporated into **v8** of the script.

The session covered one feature addition:

1. **v8** — Introduction of a session-level date/year cache so that, when multiple
   files of the same timestamp type are converted in a single batch, the recording
   date or year is asked only once (for the first file) and reused automatically for
   all subsequent files of the same type.

---

## 2. Background — Timestamp Formats

The converter handles two distinct flight data timestamp formats, originating from two
independent recording systems on the same aircraft:

| Property | Dataset 1 | Dataset 2 |
| --- | --- | --- |
| Source | Aircraft native onboard computer | Added instrumentation system |
| Sample rate | 10 Hz | 7500 Hz |
| Timestamp format | `DDD:HH:MM:SS.sss` | Seconds since midnight (float) |
| First timestamp example | `091:13:23:59.000` | `48251.186244644` |
| Decoded start time | 13:23:59.000 | 13:44:11.186 |
| Day of Year | 091 (= 2026-04-01) | 091 (= 2026-04-01) |
| Synchronised | No | No |

### Key timestamp facts

- **Dataset 1 (DDD format):** The `DDD` field encodes the Day-of-Year (1–366). The
  year is not embedded in the timestamp and must be supplied externally.
- **Dataset 2 (seconds-since-midnight):** The timestamp is a raw float representing
  elapsed seconds since 00:00:00. Both the date and year must be supplied externally.
- The two datasets are offset by 20 minutes and 12.186 seconds at their respective
  start times and are not synchronised.

---

## 3. Prior State (v7 — before this session)

Before this session, the script (v7):

- Correctly detected both timestamp formats from the first data row of each CSV.
- Estimated the sample rate automatically from inter-sample deltas.
- For Dataset 1 (DDD): showed a compact **"Confirm Recording Year"** dialog
  (`_ask_recording_year()`) pre-filled with the current year, with a live preview
  and quick-select buttons for last year / this year / next year.
- For Dataset 2 (SECONDS): showed a full graphical **calendar date picker**
  (`_ask_recording_date()`) opening on the current month, with today highlighted in
  amber and the selected date highlighted in Siemens blue.
- Supported batch processing of multiple CSV files selected in a single file-open
  dialog.
- **Problem:** In a multi-file batch, the year/date dialog was shown separately for
  every file, even when all files were from the same recording session and therefore
  shared the same date. This was repetitive and error-prone.

---

## 4. User Input & Requirement — This Session

### 4.1 Request — Session Date/Year Cache (v8)

**User input (verbatim summary):**

> When converting a batch of files that all share the same recording date, the
> date/year dialog appears once per file. It would be better if the answer given
> for the first file was remembered and reused automatically for the rest of the
> batch, without asking again.

**Agreed behaviour:**

- For the **first** file of a given timestamp type in a batch, show the existing
  dialog (year prompt for DDD; calendar picker for SECONDS) exactly as before.
- Cache the result (year integer for DDD; `datetime.date` object or Skip sentinel
  for SECONDS) in module-level variables.
- For every **subsequent** file of the same timestamp type in the same batch, skip
  the dialog entirely and reuse the cached value silently.
- If the user clicked **Skip** on the first SECONDS file, that Skip decision is also
  cached and applied silently to all remaining SECONDS files in the batch.
- The two caches are **independent**: a DDD cache hit does not affect SECONDS files,
  and vice versa. A batch containing a mix of both types prompts once per type.
- At the **start of each new batch** (i.e. when the user clicks "Convert Another
  Batch?"), both caches are reset so the user is prompted afresh.
- The cache is **not persisted** between script runs; it lives only in memory for
  the duration of the current execution.

---

## 5. Changes Incorporated — v8

### 5.1 New module-level variables: `_session_ddd_year` and `_session_seconds_date`

Two cache variables added near the top of the file, alongside the existing
module-level globals:

```python
# ── Session-level date/year cache (reset each time the script starts) ─────────
# Stores the recording date/year chosen for the FIRST file of each timestamp
# type so that subsequent files of the same type reuse it automatically.
_session_ddd_year     = None   # int  – confirmed year for DDD files
_session_seconds_date = None   # datetime.date or False (False = user chose Skip)
```

| Variable | Type when set | Meaning of `None` | Meaning of `False` |
| --- | --- | --- | --- |
| `_session_ddd_year` | `int` | Not yet set this batch | N/A |
| `_session_seconds_date` | `datetime.date` or `False` | Not yet set this batch | User chose Skip on first SECONDS file |

### 5.2 New function: `_reset_session_date_cache()`

A small helper that resets both cache variables to `None`:

```python
def _reset_session_date_cache():
    """Reset per-batch date/year cache so each new batch starts fresh."""
    global _session_ddd_year, _session_seconds_date
    _session_ddd_year     = None
    _session_seconds_date = None
```

Called once at the start of each batch iteration in `main_conversion_process_gui()`.

### 5.3 Updated: `_resolve_file_metadata()` — cache check before each dialog

The DDD and SECONDS branches inside `_resolve_file_metadata()` were each extended
with a cache check. The dialog is only shown when the cache is empty (`None`);
otherwise the cached value is used directly.

**DDD branch (new logic):**

```python
if ts_type == 'DDD':
    global _session_ddd_year
    ddd_int, _, _, _ = _parse_ddd_timestamp(first_ts_value)
    if _session_ddd_year is not None:
        # Reuse the year confirmed for the first DDD file this batch
        chosen_year = _session_ddd_year
    else:
        provisional_date = _ddd_to_date(ddd_int, datetime.date.today().year)
        context_label    = (f'DDD:{ddd_int:03d} → '
                            f'{provisional_date.strftime("%d %B")} '
                            f'(Day {ddd_int:03d})')
        chosen_year = _ask_recording_year(root, context_label)
        _session_ddd_year = chosen_year   # cache for remaining DDD files
    recording_date = _ddd_to_date(ddd_int, chosen_year)
```

**SECONDS branch (new logic):**

```python
elif ts_type == 'SECONDS':
    global _session_seconds_date
    if _session_seconds_date is not None:
        # Reuse the date (or Skip) confirmed for the first SECONDS file
        recording_date = _session_seconds_date if _session_seconds_date is not False else None
    else:
        recording_date = _ask_recording_date(root, first_ts_value)
        # Cache: store the date object, or False to represent 'user chose Skip'
        _session_seconds_date = recording_date if recording_date is not None else False
```

### 5.4 Updated: `main_conversion_process_gui()` — cache reset per batch

One line added immediately after `total_files` is determined, before the per-file
configuration loop begins:

```python
# Reset the date/year cache so each new batch prompts the user afresh
_reset_session_date_cache()
```

### 5.5 Script statistics (v8)

| Metric | Value |
| --- | --- |
| Total lines | 975 |
| File size | 43,844 bytes |
| Syntax check | PASSED ✓ |

---

## 6. Behaviour at a Glance

| Scenario | What happens |
| --- | --- |
| File 1 of N (DDD) | Year dialog shown → user confirms → year cached |
| Files 2…N (DDD, same batch) | Year dialog **skipped** → cached year reused silently |
| File 1 of N (SECONDS) | Calendar shown → user picks date → date cached |
| Files 2…N (SECONDS, same batch) | Calendar **skipped** → cached date reused silently |
| File 1 clicks Skip (SECONDS) | Skip cached as `False` → all subsequent SECONDS files also use the `1900-01-01` placeholder |
| "Convert Another Batch?" | Both caches reset → fresh prompts for the new batch |
| Mixed DDD + SECONDS in one batch | Each type has its own independent cache — no cross-contamination |
| Script restarted | Both caches initialise to `None` — always prompts on first file |

---

## 7. Complete Dialog Flow — v8

### Dataset 1 (DDD — 10 Hz) — first file of batch

```
CSV selected
    │
    ▼
Timestamp detected → info messagebox shown
    │
    ▼
_session_ddd_year is None?
  YES → _ask_recording_year()
          • Pre-filled with current year (e.g. 2026)
          • Context: "DDD:091 → 01 April (Day 091)"
          • User confirms or edits year
          • Quick-select: 2025 | 2026 | 2027
          • Result cached in _session_ddd_year
    │
    ▼
_ddd_to_date(ddd_int, chosen_year)
  → recording_date = datetime.date(2026, 4, 1)
    │
    ▼
Channel metadata + sampling frequency GUI
    │
    ▼
Output file save dialog
    │
    ▼
EDA_AbsoluteTime = ['2026-04-01 13:23:59 ms 0']
written to .asc header
```

### Dataset 1 (DDD — 10 Hz) — subsequent files in same batch

```
CSV selected
    │
    ▼
Timestamp detected → info messagebox shown
    │
    ▼
_session_ddd_year is not None → use cached year (no dialog shown)
    │
    ▼
_ddd_to_date(ddd_int, cached_year)
  → recording_date = datetime.date(2026, 4, 1)
    │
    ▼
Channel metadata + sampling frequency GUI  [proceeds as normal]
```

### Dataset 2 (SECONDS — 7500 Hz) — first file of batch

```
CSV selected
    │
    ▼
Timestamp detected → info messagebox shown
    │
    ▼
_session_seconds_date is None?
  YES → _ask_recording_date()
          • Calendar opens on current month/year
          • Header states: "The current year (2026) is pre-selected"
          • User navigates and clicks a date
          • Status bar: "01 April 2026  →  Day 091 of 2026"
          • OK / ★ Today / Skip
          • Result cached in _session_seconds_date
    │
    ▼
recording_date = datetime.date(2026, 4, 1)  [or None if Skip]
    │
    ▼
Channel metadata + sampling frequency GUI
    │
    ▼
Output file save dialog
    │
    ▼
EDA_AbsoluteTime = ['2026-04-01 13:44:11 ms 186.244644']
written to .asc header
```

### Dataset 2 (SECONDS — 7500 Hz) — subsequent files in same batch

```
CSV selected
    │
    ▼
Timestamp detected → info messagebox shown
    │
    ▼
_session_seconds_date is not None → use cached date (no dialog shown)
    │
    ▼
recording_date = cached datetime.date  [or None if cached value is False]
    │
    ▼
Channel metadata + sampling frequency GUI  [proceeds as normal]
```

---

## 8. Output Format — EDA_AbsoluteTime

The `EDA_AbsoluteTime` field written to the `.asc` header is unchanged from v6/v7:

```
EDA_AbsoluteTime = ['YYYY-MM-DD HH:MM:SS ms mmm.mmmmmm']
```

### Examples

| Scenario | Output |
| --- | --- |
| Dataset 1, DOY 091, year 2026 | `'2026-04-01 13:23:59 ms 0'` |
| Dataset 2, date picked 2026-04-01 | `'2026-04-01 13:44:11 ms 186.244644'` |
| Dataset 2, user clicked Skip | `'1900-01-01 13:44:11 ms 186.244644'` |

---

## 9. Functions Added / Modified — Summary Table

| Function | Version | Action | Description |
| --- | --- | --- | --- |
| `_session_ddd_year` | v8 | Added (global) | Cache variable — confirmed year for DDD files |
| `_session_seconds_date` | v8 | Added (global) | Cache variable — confirmed date for SECONDS files |
| `_reset_session_date_cache()` | v8 | Added | Resets both cache variables to `None` |
| `_resolve_file_metadata()` | v8 | Modified | DDD and SECONDS branches check cache before showing dialog |
| `main_conversion_process_gui()` | v8 | Modified | Calls `_reset_session_date_cache()` at the start of each batch |

---

## 10. Design Decisions & Rationale

| Decision | Rationale |
| --- | --- |
| Cache per timestamp type, not globally | DDD and SECONDS files may coexist in one batch; each type needs its own independent answer |
| `False` sentinel for Skip | Distinguishes "not yet asked" (`None`) from "asked and user chose Skip" (`False`); allows Skip to be cached and reused correctly |
| Reset on each new batch, not on each file | The whole point is to avoid re-asking within a batch; resetting per-batch ensures a fresh prompt when the user starts a genuinely new set of files |
| No reset on script restart needed | Module-level variables initialise to `None` on import — the first file of any run always prompts |
| No UI change for the user | The cache is entirely transparent; the user sees the dialog once and the rest of the batch just works |
| Cache lives in memory only | No persistence to disk — avoids stale dates being silently applied across separate script runs on different days |

---

## 11. Known Issues & Outstanding Items

| Item | Status | Notes |
| --- | --- | --- |
| `EDA_AbsoluteTime` format verification | Open | The exact string format expected by Simcenter Testlab should be verified against a known-good `.asc` file to confirm the field syntax is correct. |
| Excel OLE error | Pre-existing / external | Unrelated to this script. Caused by Excel installation issue. Recommended fix: Office Online Repair. |
| Configuration file | Future consideration | Default units, sampling frequencies, and channel mappings could be persisted in a JSON/INI file. |
| Per-file date override | Future consideration | If files in a batch span multiple recording dates, the user currently has no way to override the cached date mid-batch. A future version could offer an "Override date for this file" option. |

---

## 12. File Version History

| Version | Key Change |
| --- | --- |
| v1–v3 | Initial CLI → GUI transition; unified metadata dialog; scrollable channel list |
| v4 | Timestamp auto-detection; sample rate estimation; `EDA_AbsoluteTime` support; DOY text-entry dialog |
| v5 | Replaced DOY text-entry with full graphical calendar picker (Dataset 2 only) |
| v6 | Added current-year assumption + user-editable year prompt for both timestamp formats |
| v7 | Batch multi-file selector; per-file "File N of N" banner; batch summary dialog; skip/abort logic |
| **v8** | **Session-level date/year cache — dialog shown once per timestamp type per batch** |

---

Document generated by SiemensGPT — 20 June 2026
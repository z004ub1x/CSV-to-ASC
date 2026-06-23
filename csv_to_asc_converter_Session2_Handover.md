# CSV to ASC Converter — Development Handover Document (Session 2)

**Document Date:** 20 June 2026
**Project:** Python-based CSV to Simcenter Testlab ASC Converter — Continued Enhancement
**Primary Contact:** Myles
**AI Assistant:** SiemensGPT

---

## 1. Overview

This document records all user inputs, requirements, and code changes made during the
second development session for the `csv_to_asc_converter_GUI` Python script. It is
intended to complement the earlier handover document (dated 24 April 2026) and serves
as a complete reference for the changes incorporated into **v5** and **v6** of the script.

The session covered two major feature additions:

1. **v5** — Replacement of the day-of-year (DOY) text-entry dialog with a full
   graphical calendar date picker for Dataset 2 (seconds-since-midnight) timestamps.
2. **v6** — Addition of a current-year assumption with a user-editable year prompt,
   applied to **both** timestamp formats (DDD and seconds-since-midnight).

---

## 2. Background — Timestamp Formats

The converter handles two distinct flight data timestamp formats, originating from two
independent recording systems on the same aircraft:

| Property | Dataset 1 | Dataset 2 |
|---|---|---|
| Source | Aircraft native onboard computer | Added instrumentation system |
| Sample rate | 10 Hz | 7500 Hz |
| Timestamp format | `DDD:HH:MM:SS.sssssssss` | Seconds since midnight (float) |
| First timestamp example | `091:13:23:59.000000000` | `49451.186244644` |
| Decoded start time | 13:23:59.000 | 13:44:11.186 |
| Day of Year | 091 (= 2026-04-01) | 091 (= 2026-04-01) |
| Synchronised | No | No |

### Key timestamp facts

- **Dataset 1 (DDD format):** The `DDD` field encodes the Day-of-Year (1–366). The
  year is **not** embedded in the timestamp and must be supplied externally.
- **Dataset 2 (seconds-since-midnight):** The timestamp is a raw float representing
  elapsed seconds since 00:00:00. Both the date and year must be supplied externally.
- The two datasets are offset by **20 minutes and 12.186 seconds** at their respective
  start times and are not synchronised.

---

## 3. Prior State (v4 — before this session)

Before this session, the script:

- Correctly detected both timestamp formats from the first data row of the CSV.
- Estimated the sample rate automatically from inter-sample deltas.
- Wrote `EDA_AbsoluteTime` to the `.asc` header.
- For **Dataset 1 (DDD):** derived the date from the DDD field but used a hardcoded
  base year of 1900 (via `datetime.datetime(1900, 1, 1) + timedelta(days=ddd-1)`),
  producing incorrect dates such as `1900-04-01`.
- For **Dataset 2 (SECONDS):** prompted the user to type a 3-digit Day-of-Year number
  via a plain text entry dialog (`_ask_day_of_year`), which was unintuitive and
  error-prone. The year was also not handled, defaulting to `1900-01-01`.

---

## 4. User Inputs & Requirements — This Session

### 4.1 Request 1 — Calendar Date Picker (v5)

**User input (verbatim summary):**
> Replace the day-of-year text-entry dialog with a proper calendar GUI so users can
> simply click the recording date rather than having to know and type the DOY number.

**Agreed behaviour:**
- Show a full month-view calendar widget built entirely from `tkinter` (no external
  dependencies such as `tkcalendar`).
- Pre-open the calendar on the **current month and year**.
- Highlight today's date in amber.
- Highlight the selected date in Siemens blue (`#0078d4`).
- Show a live status bar displaying the selected date and its automatically calculated
  Day-of-Year, e.g. `01 April 2026  →  Day 091 of 2026`.
- Provide ‹ Prev and Next › buttons to navigate months (wrapping correctly across year
  boundaries).
- Provide a ★ Today button to jump instantly to today's date.
- Provide OK and Skip buttons. Skip falls back to the `1900-01-01` placeholder.
- The user never needs to see or type a DOY number.

**Scope:** Dataset 2 (seconds-since-midnight) only. Dataset 1 (DDD) was not yet
addressed in this request.

---

### 4.2 Request 2 — Current Year Assumption with User Prompt (v6)

**User input (verbatim summary):**
> Can you please add another feature whereby the absolute time value written assumes
> the current year? And for the different 10Hz format, can you please include the same
> assumption? Can you please prompt the user so they can change the year if they would
> like to do so?

**Agreed behaviour:**

#### For Dataset 1 (DDD — 10 Hz format):
- After timestamp detection, show a compact **"Confirm Recording Year"** dialog.
- Pre-fill the year field with `datetime.date.today().year` (the current calendar year).
- Show a context label such as `DDD:091 → 01 April (Day 091)` so the user can verify
  the implied date.
- Provide a live preview that updates as the user types, e.g. `→ Year accepted: 2026`.
- Provide quick-select buttons for last year, this year, and next year.
- OK commits the year; Cancel keeps the default (current year).
- Convert DDD + confirmed year to a `datetime.date` using:
  ```
  jan1 = datetime.date(year, 1, 1)
  recording_date = jan1 + datetime.timedelta(days=ddd_int - 1)
  ```
  This correctly handles leap years.

#### For Dataset 2 (SECONDS — 7500 Hz format):
- The existing calendar picker already opens on the current year by default
  (`view_year = today.year`).
- The dialog header text is updated to explicitly state:
  *"The current year (YYYY) is pre-selected."*
- No separate year prompt is needed; the user navigates the calendar to any
  month/year they require.

#### Shared behaviour:
- Both formats feed into the same `_format_eda_absolute_time()` function.
- The function now always uses a proper `datetime.date` object (never a hardcoded
  1900 base year) when a recording date has been resolved.
- The `1900-01-01` placeholder is only used if the user explicitly clicks **Skip**
  on the Dataset 2 calendar.

---

## 5. Changes Incorporated — v5

### 5.1 New function: `_ask_recording_date(root, first_ts_value)`

Replaces the old `_ask_day_of_year()` dialog entirely.

| Feature | Detail |
|---|---|
| Widget type | `tk.Toplevel` with `tk.Button` day cells and `ttk` navigation |
| Default view | Current month and year (`datetime.date.today()`) |
| Today highlight | Amber background (`#fff3e0`), bold orange text |
| Selected highlight | Siemens blue (`#0078d4`), white text |
| Month navigation | ‹ Prev / Next › buttons; wraps across year boundaries |
| Status bar | Live display: `01 April 2026  →  Day 091 of 2026` |
| ★ Today button | Jumps to and selects today's date instantly |
| OK button | Commits the selected date; warns if no day has been clicked |
| Skip button | Returns `None`; `EDA_AbsoluteTime` date falls back to `1900-01-01` |
| DOY calculation | `date.timetuple().tm_yday` — Python standard library, no dependencies |
| Return type | `datetime.date` or `None` |

### 5.2 Removed: `_ask_day_of_year()`

The old plain-text DOY entry dialog was removed entirely. All references updated.

### 5.3 Updated: `_format_eda_absolute_time()`

- DDD branch: date now derived from `recording_date` parameter (a `datetime.date`)
  rather than the old hardcoded 1900 base-year arithmetic.
- SECONDS branch: unchanged in logic; uses `recording_date` from the calendar picker.

### 5.4 Updated: `get_simcenter_header_attributes_from_csv_gui()`

- For `ts_type == 'SECONDS'`: calls `_ask_recording_date()` instead of
  `_ask_day_of_year()`.
- `recording_date` (a `datetime.date` or `None`) is passed through `ts_info` to
  `create_simcenter_asc_file()`.

### 5.5 Script statistics (v5)

| Metric | Value |
|---|---|
| Total lines | 755 |
| File size | 33,201 bytes |
| Syntax check | PASSED ✓ |

---

## 6. Changes Incorporated — v6

### 6.1 New function: `_ask_recording_year(root, context_label, default_year=None)`

A compact, reusable year-confirmation dialog used by the DDD flow.

| Feature | Detail |
|---|---|
| Default year | `datetime.date.today().year` (current calendar year) |
| Context label | Shows e.g. `DDD:091 → 01 April (Day 091)` |
| Year entry | Pre-filled, fully editable, auto-selected on open |
| Live preview | Updates on every keystroke; shows `→ Year accepted: 2026` or a warning |
| Validation | Accepts years 1900–2999 only; shows warning on invalid input |
| Quick-select | Three buttons: last year, this year, next year |
| Return binding | `<Return>` key triggers OK |
| OK | Commits the year; validates before closing |
| Cancel | Keeps the default year (current year); closes dialog |
| Return type | `int` (year) |

### 6.2 New function: `_ddd_to_date(ddd_int, year)`

Converts a Day-of-Year integer and a year into a `datetime.date`, correctly handling
leap years:

```python
jan1 = datetime.date(year, 1, 1)
return jan1 + datetime.timedelta(days=ddd_int - 1)
```

### 6.3 Updated: `_format_eda_absolute_time()`

- **DDD branch:** Now uses `recording_date.strftime('%Y-%m-%d')` (a `datetime.date`
  built from DDD + user-confirmed year) instead of any hardcoded base year.
- **SECONDS branch:** Unchanged in logic; uses `recording_date` from the calendar
  picker (which already carries the correct year from the user's selection).
- Fallback to `'1900-01-01'` only occurs if `recording_date is None` (i.e., user
  clicked Skip on the Dataset 2 calendar).

### 6.4 Updated: `get_simcenter_header_attributes_from_csv_gui()`

New DDD handling block:

```python
if ts_type == 'DDD':
    ddd_int, _, _, _ = _parse_ddd_timestamp(first_ts_value)
    provisional_date = _ddd_to_date(ddd_int, datetime.date.today().year)
    context_label    = (f'DDD:{ddd_int:03d} → '
                        f'{provisional_date.strftime("%d %B")} '
                        f'(Day {ddd_int:03d})')
    chosen_year    = _ask_recording_year(root, context_label)
    recording_date = _ddd_to_date(ddd_int, chosen_year)
```

Updated SECONDS handling — calendar header text now explicitly states the current
year is pre-selected:

```
"The current year (YYYY) is pre-selected.
Select the date on which this recording was made.
The Day-of-Year will be calculated automatically."
```

### 6.5 Updated: `_ask_recording_date()` header text

Informational label updated to include:

> *"The current year (YYYY) is pre-selected."*

This makes the year assumption explicit to the user before they interact with the
calendar.

### 6.6 Script statistics (v6)

| Metric | Value |
|---|---|
| Total lines | 892 |
| File size | 39,009 bytes |
| Syntax check | PASSED ✓ |
| All spot-checks | PASSED ✓ (12/12) |

---

## 7. Complete Dialog Flow — v6

### Dataset 1 (DDD — 10 Hz)

```
CSV selected
    │
    ▼
Timestamp detected → info messagebox shown
    │
    ▼
_ask_recording_year()
  • Pre-filled with current year (e.g. 2026)
  • Context: "DDD:091 → 01 April (Day 091)"
  • User confirms or edits year
  • Quick-select: 2025 | 2026 | 2027
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

### Dataset 2 (SECONDS — 7500 Hz)

```
CSV selected
    │
    ▼
Timestamp detected → info messagebox shown
    │
    ▼
_ask_recording_date()
  • Calendar opens on current month/year
  • Header states: "The current year (2026) is pre-selected"
  • User navigates and clicks a date
  • Status bar: "01 April 2026  →  Day 091 of 2026"
  • OK / ★ Today / Skip
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

---

## 8. Output Format — EDA_AbsoluteTime

The `EDA_AbsoluteTime` field written to the `.asc` header follows this format:

```
EDA_AbsoluteTime = ['YYYY-MM-DD HH:MM:SS ms mmm.mmmmmm']
```

### Examples

| Scenario | Output |
|---|---|
| Dataset 1, DOY 091, year 2026 | `EDA_AbsoluteTime = ['2026-04-01 13:23:59 ms 0']` |
| Dataset 2, date picked 2026-04-01 | `EDA_AbsoluteTime = ['2026-04-01 13:44:11 ms 186.244644']` |
| Dataset 2, user clicked Skip | `EDA_AbsoluteTime = ['1900-01-01 13:44:11 ms 186.244644']` |

---

## 9. Functions Added / Modified — Summary Table

| Function | Version | Action | Description |
|---|---|---|---|
| `_ask_recording_date()` | v5 | **Added** | Full calendar date picker (Dataset 2) |
| `_ask_day_of_year()` | v5 | **Removed** | Replaced by calendar picker |
| `_format_eda_absolute_time()` | v5 | **Modified** | Uses `datetime.date` for DDD branch |
| `get_simcenter_header_attributes_from_csv_gui()` | v5 | **Modified** | Calls calendar picker for SECONDS |
| `_ask_recording_year()` | v6 | **Added** | Year confirmation dialog (both formats) |
| `_ddd_to_date()` | v6 | **Added** | DDD + year → `datetime.date` (leap-year safe) |
| `_format_eda_absolute_time()` | v6 | **Modified** | Uses confirmed year for DDD branch |
| `get_simcenter_header_attributes_from_csv_gui()` | v6 | **Modified** | Year prompt for DDD; updated SECONDS text |
| `_ask_recording_date()` | v6 | **Modified** | Header text updated to state current year |

---

## 10. Design Decisions & Rationale

| Decision | Rationale |
|---|---|
| Current year as default | The vast majority of recordings are recent; this eliminates the most common source of error (wrong year) with zero user effort |
| Year prompt for DDD, calendar for SECONDS | DDD only needs a year (the day is already known); SECONDS needs a full date — different tools for different needs |
| `_ddd_to_date()` uses `timedelta` not `strptime` | Correctly handles leap years without any format-string fragility |
| Year range 1900–2999 | Broad enough for any plausible flight data; prevents nonsensical values |
| Quick-select year buttons | Covers the most common cases (last year, this year, next year) with a single click |
| Calendar opens on current month | Minimises navigation for recent recordings; user can still navigate to any past month |
| No `tkcalendar` dependency | Script remains self-contained and portable; works in any environment with standard Python |
| `1900-01-01` placeholder on Skip | Preserves Simcenter Testlab compatibility while making it obvious the date was not set |

---

## 11. Known Issues & Outstanding Items

| Item | Status | Notes |
|---|---|---|
| Excel OLE error | Pre-existing / external | Unrelated to this script. Caused by Excel installation issue. Recommended fix: Office Online Repair. |
| `EDA_AbsoluteTime` format verification | Open | The exact string format expected by Simcenter Testlab should be verified against a known-good `.asc` file to confirm the `ms` field syntax is correct. |
| Batch processing | Future consideration | Currently handled via the "Convert another file?" loop. A formal multi-file selector could be added in a future version. |
| Configuration file | Future consideration | Default units, sampling frequencies, and channel mappings could be persisted in a JSON/INI file. |

---

## 12. File Version History

| Version | Key Change |
|---|---|
| v1–v3 | Initial CLI → GUI transition; unified metadata dialog; scrollable channel list |
| v4 | Timestamp auto-detection; sample rate estimation; `EDA_AbsoluteTime` support; DOY text-entry dialog |
| **v5** | Replaced DOY text-entry with full graphical calendar picker (Dataset 2 only) |
| **v6** | Added current-year assumption + user-editable year prompt for both timestamp formats |

---

*Document generated by SiemensGPT — 20 June 2026*

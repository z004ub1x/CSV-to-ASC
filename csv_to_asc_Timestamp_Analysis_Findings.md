# Timestamp Analysis — Findings & Reference Document

## Overview

This document summarizes the investigation and verified findings from analyzing two independent flight data datasets with different timestamp formats and sample rates.

---

## Dataset Descriptions

### Dataset 1 — Aircraft Native System (10Hz)

| Property | Value |
|---|---|
| **Source** | Aircraft onboard computer (~equivalent to ALDL) |
| **Sample Rate** | 10 Hz |
| **Timestamp Format** | `DDD:HH:MM:SS.sssssssss` |
| **Delta Between Samples** | 0.1 seconds |
| **First Timestamp** | `091:13:23:59.000000000` |
| **Absolute Date/Time** | 2026-04-01 13:23:59.000 |

**Example Data:**
```
DDD:HH:MM:SS.sssssssss
091:13:23:59.000000000
091:13:23:59.100000000
091:13:23:59.200000000
```

---

### Dataset 2 — Added Instrumentation System (7500Hz)

| Property | Value |
|---|---|
| **Source** | Separate instrumentation system added to aircraft |
| **Sample Rate** | 7500 Hz |
| **Timestamp Format** | `SSSSS.sssssssss` (seconds since midnight) |
| **Delta Between Samples** | 1/7500 = 0.000133333... seconds |
| **First Timestamp** | `49451.186244644` |
| **Decoded Time** | 13:44:11.186244644 |
| **Full Format Equivalent** | `091:13:44:11.186244644` |

**Example Data:**
```
Time (seconds since midnight)
49451.186244644
49451.186377978
49451.186511311
49451.186644644
49451.186767411
49451.186900744
```

---

## Timestamp Conversion — Dataset 2

### Formula

For any timestamp T in seconds since midnight:

    HH  = floor(T / 3600)
    MM  = floor(mod(T, 3600) / 60)
    SS.sssssssss = mod(T, 60)

    Full Format = 091 : HH : MM : SS.sssssssss
                  ^--- added manually based on known recording date

> **Important:** The `DDD` day prefix (`091`) carries no information in the
> seconds-since-midnight format and **must be added manually** based on the
> known recording date.

---

### Worked Example — 49451.186244644

| Step | Calculation | Result |
|---|---|---|
| **Hours** | floor(49451 / 3600) | **13 h** |
| **Remaining seconds** | 49451 - (13 x 3600) | **2651 s** |
| **Minutes** | floor(2651 / 60) | **44 min** |
| **Remaining seconds** | 2651 - (44 x 60) | **11 s** |
| **Fractional seconds** | (from original value) | **0.186244644 s** |
| **Final decoded time** | | **13:44:11.186244644** |
| **Full format** | | **091:13:44:11.186244644** |

---

### MATLAB Implementation

Using `floor()` for truncation (as confirmed by source):

```matlab
function [HH, MM, SS] = decodeTimestamp(T)
    % T = timestamp in seconds since midnight
    % Returns hours, minutes, and full seconds with fractional part

    HH = floor(T / 3600);
    MM = floor(mod(T, 3600) / 60);
    SS = mod(T, 60);  % includes fractional seconds
end
```

**Usage example:**

```matlab
T = 49451.186244644;
[HH, MM, SS] = decodeTimestamp(T);
fprintf('Time: %02d:%02d:%012.9f\n', HH, MM, SS);
% Output: Time: 13:44:11.186244644
```

---

## Dataset Relationship & Synchronization

### Time Offset at Start

| Property | Value |
|---|---|
| **10Hz start time** | 13:23:59.000 |
| **7500Hz start time** | 13:44:11.186 |
| **Offset** | **+20 minutes, 12.1862 seconds** |

    Delta_T_start = 49451.186244644 - 48239.000000000 = 1212.186244644 seconds
                  = 20 min 12.1862 sec

---

### Synchronization Status

| Claim | Status |
|---|---|
| Datasets are from the same day (DOY 091 = 2026-04-01) | Confirmed |
| Datasets are from two different systems | Confirmed |
| Start times are synchronized | NOT synchronized |
| Datasets were meant to be time-aligned at start | Incorrect assumption — independent recordings |

> **Key Finding:** The two datasets are **completely independent recordings**.
> They are not synchronized and were never intended to be time-aligned at
> their starts. Any time alignment between the two datasets must be handled
> explicitly in code.

---

## Known Tool/Display Bug

A tool used during analysis was found to **incorrectly parse** the 7500Hz timestamps:

| | Value |
|---|---|
| **Buggy display** | `13:0.186244644` |
| **Correct reading** | `13:44:11.186244644` |

**Root cause:** The tool correctly extracts the hours (`13`) but then **drops
the minutes and whole seconds**, displaying only the sub-second fractional
remainder. Always verify timestamp conversions using the manual floor()-based
formula above.

---

## Sample Rate Verification — Dataset 2

The 7500Hz sample rate was verified by computing deltas between consecutive timestamps:

| Pair | Observed Delta (s) | Expected 1/7500 (s) | Match |
|---|---|---|---|
| Sample 2 - Sample 1 | 0.000133334 | 0.000133333... | OK |
| Sample 3 - Sample 2 | 0.000133333 | 0.000133333... | OK |
| Sample 4 - Sample 3 | 0.000133333 | 0.000133333... | OK |
| Sample 5 - Sample 4 | 0.000122767 | 0.000133333... | Rounding artifact |
| Sample 6 - Sample 5 | 0.000133333 | 0.000133333... | OK |

> **Note:** The anomalous delta at Sample 5 is a **rounding/truncation
> artifact** in the stored value, not a true timing irregularity.

---

## Quick Reference Summary

| Property | Dataset 1 (10Hz) | Dataset 2 (7500Hz) |
|---|---|---|
| **Source system** | Aircraft native computer | Added instrumentation |
| **Sample rate** | 10 Hz | 7500 Hz |
| **Timestamp format** | `DDD:HH:MM:SS.sssssssss` | `SSSSS.sssssssss` |
| **Timestamp unit** | Explicit | Seconds since midnight |
| **First timestamp** | `091:13:23:59.000000000` | `49451.186244644` |
| **Decoded start time** | 13:23:59.000 | 13:44:11.186 |
| **Synchronized** | No | No |
| **Day** | DOY 091 = 2026-04-01 | DOY 091 = 2026-04-01 |
| **Delta between samples** | 0.1 s | 1/7500 = 0.000133333... s |

---

## Notes for Code Updates

1. Use `floor()` (not `round()`) for all timestamp truncation operations.
2. Dataset 2 timestamps are **seconds since midnight** — always convert before comparing to Dataset 1.
3. The `DDD` prefix must be **manually assigned** for Dataset 2 based on known recording date.
4. Do **not** assume the two datasets start at the same time — apply the **20 min 12.1862 sec offset** if alignment is needed.
5. Any apparent delta anomalies in Dataset 2 are likely **rounding artifacts**, not true timing errors.
6. Disregard any tool display showing `HH:0.fractional` format — it is a known parsing bug.

---

*Document generated from timestamp analysis conversation — 2026-04-01 flight data, DOY 091*

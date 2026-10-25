# SiteGuard — Construction Worker & PPE Safety Detection

A Python desktop application for analysing construction-site images, videos,
webcams and IP-camera streams with a custom Ultralytics YOLO detection model.
It associates helmets and reflective jackets with workers, displays counts,
records violation episodes and exports Excel reports.

Developed by **Rupendran Manigandan** as an L&T internship project. The included
L&T visual assets are supplied project branding; this repository does not
represent an official L&T product release.

## Features

- Tkinter desktop dashboard with the updated L&T interface.
- Image, video, webcam and RTSP/HTTP camera inputs.
- Worker tracking using ByteTrack or BoT-SORT for video sources.
- Helmet and jacket counts, worker counts and compliance summaries.
- Explicit Safe, Violation and Unknown states.
- SQLite history, evidence images and optional annotated media.
- Excel `.xlsx` export with Summary, Violations and Sessions sheets.
- CSV export and daily PDF reports.
- A labelled synthetic Demo mode that works without trained weights.

## What is available

This is the recovered application source, including the UI and Excel update.
The **trained `best.pt`, training scripts, datasets, original training runs,
private records and Windows executable are not included**. The trained weights
remain on the original training computer unless separately backed up.

Demo mode runs without `best.pt`. Real detection requires a compatible custom
checkpoint. Installing the application does not recreate the trained model.

## Quick start on Windows

Install Python 3.11, 64-bit, with Tcl/Tk support. Open PowerShell in this folder.

### Interface and Demo only

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-demo.txt
.\.venv\Scripts\python.exe app_lnt.py
```

Select **Live monitoring → Demo → Start monitoring**. Demo illustrations and
counts are synthetic, not model predictions. Demo records are stored separately.

### Full detection installation

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app_lnt.py
```

Alternatively, run `setup_windows.bat`, then `start_lnt_ui.bat`.
If you already installed Demo dependencies, install `requirements.txt` into
that same environment to add detection dependencies.

Dependency installation needs internet. The application uses local files and
local inference after setup; an IP camera needs access to its camera network.
The dependency ranges are not a frozen copy of the original workstation.

## Analyse an image or video

1. Open **Settings & sources** and select a trusted, custom-trained `best.pt`.
2. For the original CPU workflow, select device `cpu` and resolution `640`.
3. Save the settings and open **Live monitoring**.
4. Change **Demo** to **Image** or **Video**, then select a file.
5. Click **Start monitoring**. Stop a running session before changing inputs.
6. Use **Export Excel** for the current or most recent session, or export
   filtered saved records from **Violation history**.

For webcams, use camera index `0` or the appropriate index. For IP cameras,
enter the stream URL in Settings. Input URLs are not saved in settings or
session metadata. Keep `assets/` next to `app_lnt.py`; Excel export uses the
bundled workbook template and does not require Microsoft Excel to be installed.

## Model and recorded evaluation

The model evaluated on the original workstation was **YOLO26s**, not YOLO26x.
The supplied test log covered 82 images and 760 labelled objects across ten
classes. Its aggregate results were:

| Metric | Recorded value |
|---|---:|
| Precision | 88.3% |
| Recall | 73.5% |
| mAP@0.50 | 79.6% |
| mAP@0.50:0.95 | 50.5% |

These are transcribed from the original test output. They have not been
reproduced from this source bundle because the trained checkpoint is absent.
They measure object detection on that small test set, not end-to-end worker
compliance accuracy. See [recorded evaluation](docs/MODEL_RESULTS.md).

The application's model mapping requires these five roles, with additional
classes allowed:

| Role | Example class name |
|---|---|
| Worker | `Person` |
| Helmet present | `Hardhat` |
| Helmet absent | `NO-Hardhat` |
| Jacket present | `Safety Vest` |
| Jacket absent | `NO-Safety Vest` |

Names are normalised. For other names, use `class_map.example.json` with the
correct class IDs and select it in Settings. A two-class helmet/jacket model
does not meet this worker-and-explicit-negative class contract.

The ten-class dataset used in the recorded run was:
[Construction Site Safety Image Dataset](https://www.kaggle.com/datasets/snehilsanyal/construction-site-safety-image-dataset-roboflow).
It is not redistributed here.

## Assessment rules and limitations

Both helmet and jacket must be confirmed present for **Safe**. A confirmed
explicit missing-item detection produces **Violation**. Occluded, contradictory
or ambiguous observations remain **Unknown**; no detection alone does not
establish that PPE is absent.

The association algorithm expects missing-helmet boxes around the head and
missing-jacket boxes around the torso. Inspect a dataset's annotation geometry
before assuming compatibility. A whole-person negative box can be rejected.

Video decisions normally require three consecutive analysed observations.
Still images are assessed immediately. Current-frame counts cover visible
tracks; Session latest uses the most recent state of every ID seen in the run.
Track IDs are estimates and can change after occlusion or re-entry. Counts are
not deduplicated across cameras or sessions.

**Known unresolved issue:** on the original workstation, Python terminated
during image analysis and Windows later reported bugchecks `0x50` and `0x1A`.
The cause was not established and no verified fix is included in this recovery.
Real-media UI processing should therefore be considered unverified. The
successful standalone model validation does not establish GUI stability.

## Reports and saved files

- Real sessions: `Documents/SiteGuard/records/`.
- Synthetic sessions: `Documents/SiteGuard/demo/`.
- SQLite: `safety.db` under the corresponding directory.
- Evidence and optional annotated media: per-session subdirectories.

Excel exports are snapshots of saved records, not continuously updating
workbooks. Dates refer to the analysis date; media positions identify a video
frame's source position. Session-day worker totals are tracking-ID totals,
not unique people across a site or multiple days. Live MP4 is an analysis
recording and does not guarantee wall-clock synchronisation or include audio.

## Source layout

```text
app_lnt.py              Updated L&T desktop interface (main entry point)
siteguard_ui_base.py    Shared settings, history and monitoring callbacks
siteguard_excel.py      Native XLSX export using the bundled template
app.py                  Earlier desktop interface
safety/core.py          PPE association, confirmation and counting
safety/engine.py        Model inference, capture and background pipeline
safety/storage.py       SQLite, CSV and PDF reporting
assets/                 Supplied branding and Excel report template
tests/                  Core and synthetic-pipeline regression tests
docs/                   Recorded evaluation and recovery/verification notes
```

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The recovered source passes 28 logic, synthetic-pipeline and reporting tests.
These do not validate a real checkpoint, Windows window rendering, camera
drivers or EXE packaging. See [verification notes](docs/VERIFICATION.md).

## Upload this source to GitHub

Extract the ZIP and open this folder in VS Code. Create an empty GitHub
repository, then use its actual URL in the final two commands below:

```powershell
git init
git add .
git diff --cached --stat
git commit -m "Add SiteGuard PPE detection desktop application"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/SiteGuard-PPE-Detection.git
git push -u origin main
```

The included `.gitignore` excludes environments, datasets, weights, generated
records and logs. Keep trained weights backed up separately when recovered.

Technical documentation: [Ultralytics](https://docs.ultralytics.com/).
Third-party dependencies and supplied branding retain their respective terms.

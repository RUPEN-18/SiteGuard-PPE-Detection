# Recovery and verification notes

## Recovery scope

This bundle combines the available original SiteGuard application with the
latest available L&T UI and Excel-export source from this conversation. It is
not an image of the inaccessible Windows computer. Any edits made only on
that computer cannot be recovered from these files.

Present: both desktop entry points, shared callbacks, safety backend, tests,
requirements, supplied logos, Excel template and launch/setup scripts.

Absent: trained weights, original dataset, training/resume scripts, training
CSV files, original private reports, screenshots of real predictions, the
original virtual environment and a compiled Windows EXE.

## Checks

The recovered application passes 28 unittest cases covering class mapping,
PPE geometry and association, ambiguity, conflicting detections, temporal
confirmation, worker counts, episode suppression/recovery, SQLite filtering,
synthetic evidence generation, CSV and PDF reporting, and the background Demo
pipeline. All bundled Python modules compile.

Earlier development also checked the updated controller headlessly with Tcl
variables and exercised Excel export using synthetic session data. Such
checks do not verify native Windows window layout or real-model inference.

## Unresolved original-computer failure

The user reported Python closing after starting image analysis. Windows
subsequently recorded bugcheck 0x50 and, on the previous day, 0x1A with subtype
0x41790. The screenshot also listed Python application failures and a Windows
Hardware error entry. The crash dump and application-fault details were not
analysed, and no memory-test result was obtained.

The source has not been changed to claim a solution to these failures.
Hardware, driver and native-library causes remain undetermined. A successful
standalone YOLO test run and successful Demo tests do not establish that the
image-analysis UI is stable on the original workstation.

Real-model input, camera capture, native Windows GUI rendering and Windows
packaging require separate verification once a suitable computer and model
checkpoint are available.

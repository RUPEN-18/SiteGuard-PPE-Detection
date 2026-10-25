# Recorded YOLO26s test evaluation

These values were transcribed from the user's successful Ultralytics test
output in this project conversation. The original weights and complete run
artifacts are absent from this source recovery; this is not a new evaluation.

## Configuration observed in the log

- Model: custom-trained YOLO26s, fused, 120 layers, 9,469,050 parameters.
- Ultralytics 8.4.177; Python 3.11.8; torch 2.14.1+cpu.
- Processor: Intel Core i7-12700; inference device: CPU.
- Dataset: css-data, ten classes, test split.
- Input size: 640; batch size: 4; workers: 0.
- Test population: 82 images, 760 labelled objects; 8 background images.
- Training log showed 2,605 training and 114 validation images.
- Validation history was supplied through epoch 54; a later training progress
  line showed epoch 55/76. The exact epoch of `best.pt` was not established.

## Test metrics

| Class | Images | Instances | Precision | Recall | mAP50 | mAP50-95 |
|---|---:|---:|---:|---:|---:|---:|
| All | 82 | 760 | 0.883 | 0.735 | 0.796 | 0.505 |
| Hardhat | 30 | 110 | 0.990 | 0.912 | 0.955 | 0.630 |
| Mask | 16 | 28 | 0.971 | 0.750 | 0.745 | 0.534 |
| NO-Hardhat | 25 | 41 | 0.756 | 0.585 | 0.599 | 0.344 |
| NO-Mask | 30 | 79 | 0.796 | 0.722 | 0.768 | 0.323 |
| NO-Safety Vest | 36 | 90 | 0.973 | 0.778 | 0.830 | 0.501 |
| Person | 59 | 174 | 0.844 | 0.807 | 0.875 | 0.587 |
| Safety Cone | 8 | 92 | 0.809 | 0.478 | 0.529 | 0.247 |
| Safety Vest | 22 | 61 | 0.889 | 0.789 | 0.897 | 0.624 |
| machinery | 22 | 44 | 0.900 | 0.795 | 0.890 | 0.683 |
| vehicle | 15 | 41 | 0.901 | 0.732 | 0.869 | 0.573 |

Class image counts overlap because one image can contain several classes.

Recorded speed per image: 0.8 ms preprocessing, 87.5 ms inference and 1.2 ms
postprocessing in this batched validation run. This is not a measured live
application frame rate.

## Interpretation

The strongest reported helmet-present result was Hardhat mAP50 0.955.
NO-Hardhat recall was 0.585, indicating a substantial missed-detection issue
for that class in this evaluation. End-to-end compliance also depends on
person detection, PPE-to-person association, tracking and confirmation.
No single percentage here should be labelled overall worker-safety accuracy.

## Reproduction when the weights are recovered

The dataset YAML must point to the correct local dataset and retain the same
class order. From an environment with the necessary dependencies:

```powershell
.\.venv\Scripts\yolo.exe detect val model="PATH_TO_RECOVERED_BEST_PT" data="PATH_TO_DATA_YAML" split=test imgsz=640 batch=4 device=cpu workers=0 verbose=True
```

Dataset class order reported in the original run:

```text
0 Hardhat
1 Mask
2 NO-Hardhat
3 NO-Mask
4 NO-Safety Vest
5 Person
6 Safety Cone
7 Safety Vest
8 machinery
9 vehicle
```

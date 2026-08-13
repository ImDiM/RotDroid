# RotDroid: Cross-Orientation State Equivalence Testing for Detecting GUI Rotation Bugs in Android Apps

This repository supports the replication of our study “RotDroid: Cross-Orientation State Equivalence Testing for Detecting GUI Rotation Bugs in Android Apps” accepted for publication at The 37th IEEE International Symposium on Software Reliability Engineering (ISSRE 2026).

## Artifact links

- This code repository contains RotDroid and the RotBench construction pipeline.
- RotVL models: available at [Hugging Face](https://huggingface.co/ImDim/RotVL)
- RotBench dataset: available at [Hugging Face](https://huggingface.co/datasets/ImDim/RotBench)
- Full Artifact with VM image and full-apks: available at [Zenodo](https://doi.org/10.5281/zenodo.21897206)

## Expected behaviour

RotDroid explores Android applications on two devices or emulators, constructs UI transition graphs, captures corresponding portrait/landscape states, and queries RotVL for rotation-induced GUI bugs.
Its output contains captured states, screenshot pairs, model predictions, logs, and UTG files under the directory specified by `--out-dir`.

The RotBench pipeline collects right screenshot pairs and performs deduplication, synthesis of five bug types, image compression, metadata generation, project-level splitting, and dataset construction.

## Repository structure

```text
.
├── README.md                    This guide
├── ISSUES.md                    78 detected open-source app issues and their status
├── rotdroid.py                  RotDroid entry point
├── rotbench.py                  RotBench construction entry point
├── requirements-host.txt        Python dependencies
├── configs/                     Prompts and API-token template
├── explorer/                    Exploration, state, SRS, and UTG modules
├── models/                      Model interfaces and API/vLLM clients
├── rotbench_construction/       RotBench construction functions
├── finetune/                    Model-output parsing
├── utils/                       APK, device, file, logging, and UI utilities
├── tools/apktool_2.11.1.jar     Bundled Apktool
├── demo-apk/                    One APK for the RotDroid smoke test
└── demo-apks/                   Four APKs for RotBench testing, not the full corpus
```

## Environment setup

Recommended client environment:

- **Host:** at least 16 GiB RAM, 6 logical CPU cores, and 80 GiB free space
- **Python:** 3.10 or later
- **Tools:** OpenJDK 17, ADB, Android Emulator with two AVDs, Android Build-Tools (`zipalign` and `apksigner`), Apktool 2.11.1, Tesseract, and Graphviz

Model-backed runs require a separate Linux CUDA server. Start a downloaded RotVL model as an OpenAI-compatible service:

```bash
CUDA_VISIBLE_DEVICES=0 VLLM_ALLOW_LONG_MAX_MODEL_LEN=1 \
vllm serve <ROTVL_MODEL_PATH> \
  --served-model-name <ROTVL_MODEL_NAME> \
  --limit-mm-per-prompt '{"image": 2}' \
  --host 0.0.0.0 \
  --port 8000 \
  --dtype float16 \
  --api-key xxx \
  --max-model-len 32768 \
  --tensor-parallel-size 1
```

## Quick start

### A. Construct RotBench

Collect right portrait/landscape screenshot pairs. The `demo-apks` directory provides a small APK set for testing, while the complete APK corpus is provided as `full-apks.zip` in the full artifact:

```bash
python rotbench.py collect \
  --apks-dir demo-apks \
  --output-dir output_rotbench/pairs \
  --metadata-path output_rotbench/metadata/projects.jsonl \
  --log-path output_rotbench/collect.log \
  --device-id emulator-5554 \
  --avd Pixel_6a_API_33
```

Manually remove any defective portrait/landscape screenshot pairs from `output_rotbench/pairs/capture`.

Then start Qwen2.5-VL-7B-Instruct with vLLM or another OpenAI-compatible server and run the remaining stages:

```bash
python rotbench.py pipeline \
  --pairs-dir output_rotbench/pairs/capture \
  --work-dir output_rotbench \
  --output-dir rotbench_demo \
  --tesseract-cmd /usr/bin/tesseract \
  --model-name Qwen2.5-VL-7B-Instruct \
  --model-base-url http://<MODEL_SERVER>:8000/v1 \
  --model-api-key xxx
```

The output contains six train/validation/test JSON files and `stats.jsonl`; the default project split is 80%/10%/10%.

### B. Run RotDroid

Prepare the paper APK list and two clean Android devices, start the RotVL service, and run:

```bash
python rotdroid.py \
  --apk-list-file <PAPER_APK_LIST> \
  --out-dir output_rotdroid \
  --device-names Pixel_6a_API_33 Pixel_6a_API_33_2 \
  --android-port 5554 5556 \
  --algo random \
  --iter-cnt 15000 \
  --srs-ratio 0.1 \
  --app-time-limit-minutes 30 \
  --model-name <ROTVL_MODEL_NAME> \
  --model-base-url http://<MODEL_SERVER>:8000/v1 \
  --model-api-key xxx \
  --clear
```

Successful execution creates a package directory containing `curstate/`, `pairs/pairs.jsonl`, `pairs/success_pairs.jsonl`, `detect_result.jsonl`, and `utg/`.

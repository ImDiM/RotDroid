
from __future__ import annotations

import argparse
import importlib
import json
import sys
import types
from pathlib import Path
from typing import Any, Sequence


CODE_DIR = Path(__file__).resolve().parent
CONSTRUCTION_DIR = CODE_DIR / "rotbench_construction"


PROJECT_DIR = CODE_DIR


def path_arg(value: str) -> Path:
    return Path(value).expanduser()


def require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{label} does not exist: {path}")


def require_dir(path: Path, label: str) -> None:
    if not path.is_dir():
        raise NotADirectoryError(f"{label} does not exist: {path}")


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def lightweight_package(name: str, directory: Path):
    package = sys.modules.get(name)
    if package is not None:
        return package
    package = types.ModuleType(name)
    package.__package__ = name
    package.__path__ = [str(directory)]
    sys.modules[name] = package
    return package


def prepare_internal_imports(module_name: str) -> None:
    if module_name in {"collect_pairs", "augment_pairs"}:
        models_package = lightweight_package("models", PROJECT_DIR / "models")
        importlib.import_module("models.model")
        if module_name == "augment_pairs":
            factory = importlib.import_module("models.model_factory")
            messages = importlib.import_module("models.message_manager")
            models_package.ModelFactory = factory.ModelFactory
            models_package.VLMMessager = messages.VLMMessager

            explorer_package = lightweight_package(
                "explorer", PROJECT_DIR / "explorer"
            )
            mark = importlib.import_module("explorer.mark")
            explorer_package.mark_shape = mark.mark_shape


def load_module(name: str):
    for directory in (PROJECT_DIR, CONSTRUCTION_DIR):
        value = str(directory)
        if value not in sys.path:
            sys.path.insert(0, value)
    prepare_internal_imports(name)
    return importlib.import_module(name)


def collect_command(args: argparse.Namespace) -> Path:
    apks_dir = path_arg(args.apks_dir)
    output_dir = path_arg(args.output_dir)
    metadata_path = path_arg(args.metadata_path)
    apktool_jar = path_arg(args.apktool_jar)
    log_path = path_arg(args.log_path)
    require_dir(apks_dir, "APK directory")
    require_file(apktool_jar, "apktool JAR")
    ensure_parent(metadata_path)
    metadata_path.touch(exist_ok=True)
    ensure_parent(log_path)

    from utils import config_log, restart_emulator

    config_log(str(log_path), clear=args.clear_log)
    device_id = args.device_id
    if args.restart_emulator:
        device_id = restart_emulator(device_id, avd=args.avd)

    module = load_module("collect_pairs")
    module.collect_all(
        device_id,
        str(apks_dir),
        str(output_dir),
        str(metadata_path),
        str(apktool_jar),
        repack_apk=args.repack_apk,
        recapture=args.recapture,
    )
    return output_dir / "capture"


def deduplicate_command(args: argparse.Namespace) -> Path:
    image_directory = path_arg(args.image_directory)
    hash_path = path_arg(args.hash_path)
    require_dir(image_directory, "Screenshot-pair directory")
    ensure_parent(hash_path)
    output_path = Path(str(image_directory).replace("capture", args.output_replace))
    if output_path == image_directory:
        raise ValueError(
            "The input path must contain 'capture', because process_duplicates() "
            "constructs its output path by replacing that component"
        )

    module = load_module("dedup_pairs")
    duplicates = module.deduplicate_images(
        str(image_directory), threshold=args.threshold
    )

    from utils.file_utils import write_json

    write_json(str(hash_path), duplicates)
    module.process_duplicates(duplicates, args.output_replace)
    return output_path


def augment_command(args: argparse.Namespace) -> Path:
    input_dir = path_arg(args.input_dir)
    output_dir = path_arg(args.output_dir)
    metadata_path = path_arg(args.metadata_path)
    log_path = path_arg(args.log_path)
    require_dir(input_dir, "Normal screenshot-pair directory")
    ensure_parent(metadata_path)
    ensure_parent(log_path)

    from utils import clear_dir, clear_jsonl, config_log

    if args.reconstruct:
        clear_dir(str(output_dir))
        clear_jsonl(str(metadata_path))
    config_log(str(log_path), clear=args.reconstruct or args.clear_log)
    if args.ocr_temp_dir:
        clear_dir(str(path_arg(args.ocr_temp_dir)))

    module = load_module("augment_pairs")
    if args.tesseract_cmd:
        module.pytesseract.pytesseract.tesseract_cmd = str(
            path_arg(args.tesseract_cmd)
        )
    module.augment(
        str(input_dir),
        str(output_dir),
        str(metadata_path),
        reconstruct=args.reconstruct,
        model_config={
            "name": args.model_name,
            "base_url": args.model_base_url,
            "api_key": args.model_api_key,
            "temperature": 0.7,
            "max_token": 25,
        },
    )
    return metadata_path


def right_metadata_command(args: argparse.Namespace) -> Path:
    input_dir = path_arg(args.input_dir)
    output_path = path_arg(args.output_path)
    require_dir(input_dir, "Normal screenshot-pair directory")
    ensure_parent(output_path)

    from utils import clear_jsonl

    if args.clear:
        clear_jsonl(str(output_path))
    load_module("finetune_data").construct_right(str(input_dir), str(output_path))
    return output_path


def build_command(args: argparse.Namespace) -> dict[str, Any]:
    bug_file = path_arg(args.bug_file)
    right_file = path_arg(args.right_file)
    projects_dir = path_arg(args.projects_dir)
    output_dir = path_arg(args.output_dir)
    stats_path = path_arg(args.stats_path)
    require_file(bug_file, "Bug metadata")
    require_file(right_file, "Normal-pair metadata")
    require_dir(projects_dir, "Project directory")
    output_dir.mkdir(parents=True, exist_ok=True)
    ensure_parent(stats_path)

    from utils import append_jsonl, clear_jsonl

    module = load_module("finetune_data")
    clear_jsonl(str(stats_path))
    parameters = {
        "random_state": args.random_state,
        "bug_file": str(bug_file),
        "right_file": str(right_file),
        "projs_dir": str(projects_dir),
        "output_dir": str(output_dir),
        "proj_cnt": args.project_count,
    }
    append_jsonl(str(stats_path), parameters)

    common = {
        "bug_file": str(bug_file),
        "projs_dir": str(projects_dir),
        "output_dir": str(output_dir),
        "proj_cnt": args.project_count,
        "train_ratio": args.train_ratio,
        "val_ratio": args.validation_ratio,
        "test_ratio": args.test_ratio,
        "min_pixels": args.min_pixels,
        "max_pixels": args.max_pixels,
        "random_state": args.random_state,
    }
    detection_stats = module.lf_datasets_two(
        right_file=str(right_file),
        save_train=args.detection_train,
        save_val=args.detection_validation,
        save_test=args.detection_test,
        **common,
    )
    append_jsonl(str(stats_path), detection_stats)

    localization_stats = module.lf_datasets_multi(
        save_train=args.localization_train,
        save_val=args.localization_validation,
        save_test=args.localization_test,
        **common,
    )
    append_jsonl(str(stats_path), localization_stats)

    if args.detection_test_common:
        module.lf_to_common(
            str(output_dir / args.detection_test),
            str(path_arg(args.detection_test_common)),
        )
    if args.localization_test_common:
        module.lf_to_common(
            str(output_dir / args.localization_test),
            str(path_arg(args.localization_test_common)),
        )

    result = {
        "bug_detection": detection_stats,
        "bug_classification_and_localization": localization_stats,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def pipeline_command(args: argparse.Namespace) -> None:
    pairs_dir = path_arg(args.pairs_dir)
    require_dir(pairs_dir, "Screenshot-pair directory")
    work_dir = path_arg(args.work_dir)



    args.defect_output_dir = args.defect_output_dir or str(work_dir / "defective")
    args.right_compressed_dir = args.right_compressed_dir or str(work_dir / "right_comp")
    args.defect_compressed_dir = args.defect_compressed_dir or str(work_dir / "defective_comp")
    args.augment_log = args.augment_log or str(work_dir / "logs" / "augment.log")
    args.bug_file = args.bug_file or str(work_dir / "metadata" / "bug.jsonl")
    args.right_file = args.right_file or str(work_dir / "metadata" / "right.jsonl")
    args.stats_path = args.stats_path or str(path_arg(args.output_dir) / "stats.jsonl")
    raw_bug_file = work_dir / "metadata" / "bug_uncompressed.jsonl"
    if not args.hash_path:
        args.hash_path = str(work_dir / "metadata" / "dedup_hash.json")

    pairs_dir = deduplicate_command(
        argparse.Namespace(
            image_directory=str(pairs_dir),
            hash_path=args.hash_path,
            threshold=args.threshold,
            output_replace=args.output_replace,
        )
    )

    augment_command(
        argparse.Namespace(
            input_dir=str(pairs_dir),
            output_dir=args.defect_output_dir,
            metadata_path=str(raw_bug_file),
            log_path=args.augment_log,
            reconstruct=args.reconstruct,
            clear_log=args.clear_log,
            ocr_temp_dir=args.ocr_temp_dir,
            tesseract_cmd=args.tesseract_cmd,
            model_name=args.model_name,
            model_base_url=args.model_base_url,
            model_api_key=args.model_api_key,
        )
    )
    module = load_module("finetune_data")
    if args.reconstruct:
        from utils import clear_dir

        clear_dir(args.right_compressed_dir)
        clear_dir(args.defect_compressed_dir)
    module.resize_images(
        str(pairs_dir),
        args.right_compressed_dir,
        ratio=args.compression_ratio,
    )
    module.resize_images(
        args.defect_output_dir,
        args.defect_compressed_dir,
        ratio=args.compression_ratio,
    )
    module.ori_to_comp_jsonl(
        str(raw_bug_file),
        args.bug_file,
        ratio=args.compression_ratio,
        replace_str=args.defect_output_dir,
        replacement_str=args.defect_compressed_dir,
    )
    right_metadata_command(
        argparse.Namespace(
            input_dir=args.right_compressed_dir,
            output_path=args.right_file,
            clear=True,
        )
    )
    args.projects_dir = args.right_compressed_dir
    build_command(args)


def add_build_arguments(parser: argparse.ArgumentParser, pipeline: bool = False) -> None:
    parser.add_argument(
        "--bug-file",
        required=not pipeline,
        help="Pipeline default: WORK_DIR/metadata/bug.jsonl" if pipeline else None,
    )
    parser.add_argument(
        "--right-file",
        required=not pipeline,
        help="Pipeline default: WORK_DIR/metadata/right.jsonl" if pipeline else None,
    )
    if not pipeline:
        parser.add_argument("--projects-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--stats-path",
        required=not pipeline,
        help="Pipeline default: OUTPUT_DIR/stats.jsonl" if pipeline else None,
    )
    parser.add_argument("--project-count", type=int, default=623)
    parser.add_argument("--random-state", type=int, default=8)
    parser.add_argument("--train-ratio", type=float, default=0.8)
    parser.add_argument("--validation-ratio", type=float, default=0.1)
    parser.add_argument("--test-ratio", type=float, default=0.1)
    parser.add_argument("--min-pixels", type=int, default=4 * 28 * 28)
    parser.add_argument("--max-pixels", type=int, default=16384 * 28 * 28)
    parser.add_argument("--detection-train", default="lf_train_2_comp.json")
    parser.add_argument("--detection-validation", default="lf_val_2_comp.json")
    parser.add_argument("--detection-test", default="lf_test_2_comp.json")
    parser.add_argument("--localization-train", default="lf_train_multi_comp.json")
    parser.add_argument(
        "--localization-validation", default="lf_val_multi_comp.json"
    )
    parser.add_argument("--localization-test", default="lf_test_multi_comp.json")
    parser.add_argument("--detection-test-common")
    parser.add_argument("--localization-test-common")


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Unified wrapper for RotBench construction scripts."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    collect = commands.add_parser("collect", help="Run screenshot-pair collection")
    collect.add_argument("--apks-dir", required=True)
    collect.add_argument("--output-dir", required=True)
    collect.add_argument("--metadata-path", required=True)
    collect.add_argument(
        "--apktool-jar",
        default=str(CODE_DIR / "tools" / "apktool_2.11.1.jar"),
        help="Path to Apktool JAR (default: bundled tools/apktool_2.11.1.jar)",
    )
    collect.add_argument("--log-path", required=True)
    collect.add_argument("--device-id", default="emulator-5554")
    collect.add_argument("--avd", default="Pixel_6a_API_33")
    collect.add_argument(
        "--restart-emulator", action=argparse.BooleanOptionalAction, default=True
    )
    collect.add_argument("--repack-apk", action="store_true")
    collect.add_argument("--recapture", action="store_true")
    collect.add_argument("--clear-log", action="store_true")
    collect.set_defaults(handler=collect_command)

    dedup = commands.add_parser("deduplicate", help="Run screenshot-pair deduplication")
    dedup.add_argument("--image-directory", required=True)
    dedup.add_argument("--hash-path", required=True)
    dedup.add_argument("--output-replace", default="capture_dedup")
    dedup.add_argument("--threshold", type=int, default=5)
    dedup.set_defaults(handler=deduplicate_command)

    augment = commands.add_parser("augment", help="Run defect synthesis")
    augment.add_argument("--input-dir", required=True)
    augment.add_argument("--output-dir", required=True)
    augment.add_argument("--metadata-path", required=True)
    augment.add_argument("--log-path", required=True)
    augment.add_argument("--ocr-temp-dir")
    augment.add_argument("--tesseract-cmd")
    augment.add_argument("--model-name", default="Qwen2.5-VL-7B-Instruct")
    augment.add_argument("--model-base-url")
    augment.add_argument("--model-api-key")
    augment.add_argument("--reconstruct", action="store_true")
    augment.add_argument("--clear-log", action="store_true")
    augment.set_defaults(handler=augment_command)

    right = commands.add_parser("right-metadata", help="Construct normal-pair metadata")
    right.add_argument("--input-dir", required=True)
    right.add_argument("--output-path", required=True)
    right.add_argument("--clear", action=argparse.BooleanOptionalAction, default=True)
    right.set_defaults(handler=right_metadata_command)

    build = commands.add_parser("build", help="Build the two RotBench datasets")
    add_build_arguments(build)
    build.set_defaults(handler=build_command)

    pipeline = commands.add_parser(
        "pipeline", help="Chain the existing construction functions"
    )
    pipeline.add_argument("--pairs-dir", required=True)
    pipeline.add_argument(
        "--work-dir",
        default="rotbench_work",
        help="Base directory for automatically derived intermediate paths",
    )
    pipeline.add_argument(
        "--hash-path",
        help="Default: WORK_DIR/metadata/dedup_hash.json",
    )
    pipeline.add_argument("--output-replace", default="capture_dedup")
    pipeline.add_argument("--threshold", type=int, default=5)
    pipeline.add_argument(
        "--defect-output-dir", help="Default: WORK_DIR/defective"
    )
    pipeline.add_argument(
        "--right-compressed-dir", help="Default: WORK_DIR/right_comp"
    )
    pipeline.add_argument(
        "--defect-compressed-dir", help="Default: WORK_DIR/defective_comp"
    )
    pipeline.add_argument("--compression-ratio", type=float, default=2 / 3)
    pipeline.add_argument(
        "--augment-log", help="Default: WORK_DIR/logs/augment.log"
    )
    pipeline.add_argument("--ocr-temp-dir")
    pipeline.add_argument("--tesseract-cmd")
    pipeline.add_argument("--model-name", default="Qwen2.5-VL-7B-Instruct")
    pipeline.add_argument("--model-base-url")
    pipeline.add_argument("--model-api-key")
    pipeline.add_argument("--reconstruct", action="store_true")
    pipeline.add_argument("--clear-log", action="store_true")
    add_build_arguments(pipeline, pipeline=True)
    pipeline.set_defaults(handler=pipeline_command)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = create_parser()
    args = parser.parse_args(argv)
    try:
        args.handler(args)
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

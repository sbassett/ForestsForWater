import hashlib
import os
import inspect
import json
import datetime
from typing import Dict, List, Any
from pydantic import BaseModel, Field

# Pydantic schema for step-level cache metadata
class StepMetadata(BaseModel):
    step_name: str
    input_file_hashes: Dict[str, str] = Field(default_factory=dict)
    output_file_hashes: Dict[str, str] = Field(default_factory=dict)
    logic_hash: str
    parameters: Dict[str, str] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.datetime.now().isoformat())
    status: str = "success"

# Pydantic schema for the overall pipeline cache metadata
class PipelineMetadata(BaseModel):
    pipeline_version: str = "1.0.0"
    steps: Dict[str, StepMetadata] = Field(default_factory=dict)

def get_file_hash(file_path: str) -> str:
    """Computes the SHA256 hash of a file or a directory (like a .gdb)."""
    if not os.path.exists(file_path):
        return ""
    sha256 = hashlib.sha256()
    
    if os.path.isdir(file_path):
        # Recursively hash files in the directory to handle .gdb folders
        for root, _, files in os.walk(file_path):
            for filename in sorted(files):
                full_path = os.path.join(root, filename)
                try:
                    with open(full_path, "rb") as f:
                        while chunk := f.read(8192):
                            sha256.update(chunk)
                except Exception:
                    pass
    else:
        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                sha256.update(chunk)
    return sha256.hexdigest()


def get_logic_hash(func) -> str:
    """Computes the SHA256 hash of a function's source code to track changes in logic."""
    try:
        source_code = inspect.getsource(func)
        return hashlib.sha256(source_code.encode("utf-8")).hexdigest()
    except Exception:
        # Fallback if inspect fails (e.g. if the function is imported in a way that inspect cannot resolve)
        return hashlib.sha256(func.__name__.encode("utf-8")).hexdigest()

def should_skip_step(
    step_name: str,
    input_files: List[str],
    output_files: List[str],
    func,
    params: Dict[str, Any],
    cache_file: str
) -> bool:
    """
    Checks if all output files exist and if the current input files, function logic,
    and parameters match the cached metadata. If they all match, the step can be skipped.
    """
    # 1. Output files must exist
    for f in output_files:
        if not os.path.exists(f):
            return False

    # 2. Cache metadata file must exist
    if not os.path.exists(cache_file):
        return False

    # 3. Load and validate cache file
    try:
        with open(cache_file, "r") as f:
            data = json.load(f)
            metadata = PipelineMetadata.model_validate(data)
    except Exception as e:
        print(f"[{step_name}] Cache file invalid or corrupted, re-running step. Error: {e}")
        return False

    # 4. Check if step is in cache
    if step_name not in metadata.steps:
        return False

    cached_step = metadata.steps[step_name]

    # 5. Verify function logic hash
    current_logic_hash = get_logic_hash(func)
    if cached_step.logic_hash != current_logic_hash:
        print(f"[{step_name}] Logic modified (logic_hash mismatch). Re-running step.")
        return False

    # 6. Verify parameter match
    current_params = {k: str(v) for k, v in params.items()}
    if cached_step.parameters != current_params:
        print(f"[{step_name}] Parameters changed. Re-running step.")
        return False

    # 7. Verify input files hashes
    for f in input_files:
        current_hash = get_file_hash(f)
        if current_hash != cached_step.input_file_hashes.get(f):
            print(f"[{step_name}] Input file {f} changed. Re-running step.")
            return False

    # 8. Verify output files hashes
    for f in output_files:
        current_hash = get_file_hash(f)
        if current_hash != cached_step.output_file_hashes.get(f):
            print(f"[{step_name}] Output file {f} changed or missing in cache. Re-running step.")
            return False

    # All checks passed, skip the step
    return True

def record_step_metadata(
    step_name: str,
    input_files: List[str],
    output_files: List[str],
    func,
    params: Dict[str, Any],
    cache_file: str
):
    """Computes and records input, output, and logic hashes to the cache metadata file."""
    metadata = PipelineMetadata()
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r") as f:
                data = json.load(f)
                metadata = PipelineMetadata.model_validate(data)
        except Exception:
            pass

    input_hashes = {f: get_file_hash(f) for f in input_files}
    output_hashes = {f: get_file_hash(f) for f in output_files}
    logic_hash = get_logic_hash(func)
    params_str = {k: str(v) for k, v in params.items()}

    metadata.steps[step_name] = StepMetadata(
        step_name=step_name,
        input_file_hashes=input_hashes,
        output_file_hashes=output_hashes,
        logic_hash=logic_hash,
        parameters=params_str,
        timestamp=datetime.datetime.now().isoformat(),
        status="success"
    )

    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
    with open(cache_file, "w") as f:
        f.write(metadata.model_dump_json(indent=2))
    print(f"[{step_name}] Cache updated.")

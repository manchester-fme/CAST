#!/usr/bin/env python3
"""
Shared coverage-mapping primitives used by CAST's single, solver-agnostic
coverage_mapper.py/generate_matrix.py (also in src/coverage/). Test
discovery and single-test execution aren't per-solver code at all anymore -
they're opaque shell commands declared in each solver's manifest.json
(coverage.list_tests_command/run_test_command); this module holds the parts
that are genuinely identical regardless of which command produced a test
name: fastcov output parsing, function-name demangling, path simplification,
memory bookkeeping, and calculate_jobs (generate_matrix.py's job-count/
tests-per-job math).
"""

import gc
import json
import subprocess
from pathlib import Path
from typing import Dict, Optional, Tuple


def is_source_file(file_path: str) -> bool:
    """Check if a file path belongs to the project under test (as opposed to
    system headers, build/dependency directories, etc.) - a plain 'src/'
    directory check, with no solver-specific knowledge needed."""
    has_src_dir = 'src/' in file_path

    excluded_patterns = [
        '/usr/include/', '/usr/lib/', '/System/', '/Library/',
        '/Applications/', '/opt/', '/deps/', '/build/deps/',
        '/build/src/', '/build/', '/include/', '/lib/',
        '/bin/', '/share/', 'CMakeFiles/', 'cmake/', 'Makefile'
    ]
    has_excluded_pattern = any(exclude in file_path for exclude in excluded_patterns)

    return has_src_dir and not has_excluded_pattern


def demangle_function_name(mangled_name: str, cache: Dict[str, str]) -> str:
    """Demangle a C++ function name using c++filt, caching results in the
    caller-owned cache dict (mutated in place)."""
    if mangled_name in cache:
        return cache[mangled_name]

    try:
        result = subprocess.run(['c++filt', mangled_name], capture_output=True, text=True)
        demangled = result.stdout.strip() if result.returncode == 0 else mangled_name
        cache[mangled_name] = demangled
        return demangled
    except FileNotFoundError:
        cache[mangled_name] = mangled_name
        return mangled_name


def simplify_file_path(file_path: str) -> str:
    """Simplify a file path to show only the relevant project path starting from src/"""
    if '/src/' in file_path:
        parts = file_path.split('/src/')
        if len(parts) > 1:
            return 'src/' + parts[1]
    return file_path


def get_memory_usage_mb() -> float:
    """Get current process memory usage in MB"""
    try:
        import psutil
        process = psutil.Process()
        return process.memory_info().rss / 1024 / 1024
    except Exception:
        return 0.0


def check_memory_limit(max_memory_mb: float) -> bool:
    """Check if current memory usage is within the given limit"""
    memory_mb = get_memory_usage_mb()
    if memory_mb > max_memory_mb:
        print(f"⚠️ Memory limit exceeded: {memory_mb:.1f}MB > {max_memory_mb}MB")
        return False
    return True


def cleanup_memory(demangle_cache: Dict[str, str]) -> None:
    """Force garbage collection and clear the demangle cache once it grows large"""
    if len(demangle_cache) > 1000:
        demangle_cache.clear()
    gc.collect()


def write_intermediate_mapping(function_to_tests: Dict, output_file: Path) -> None:
    """Write intermediate function->tests mapping to disk to save memory"""
    with open(output_file, 'w') as f:
        json.dump(function_to_tests, f, separators=(',', ':'))


def parse_fastcov_json(fastcov_file: Path, test_name: str, demangle_cache: Dict[str, str]) -> Optional[Dict]:
    """Parse a fastcov JSON file to extract covered-function information"""
    with open(fastcov_file, 'r') as f:
        data = json.load(f)

    functions = set()

    if 'sources' in data:
        for file_path, file_data in data['sources'].items():
            if is_source_file(file_path):
                if '' in file_data and 'functions' in file_data['']:
                    for func_name, func_data in file_data['']['functions'].items():
                        if func_data.get('execution_count', 0) > 0:
                            demangled_name = demangle_function_name(func_name, demangle_cache)
                            simplified_path = simplify_file_path(file_path)
                            line_num = func_data.get('start_line', 0)
                            func_id = f"{simplified_path}:{demangled_name}:{line_num}"
                            functions.add(func_id)

    if not functions:
        return None

    return {
        "test_name": test_name,
        "functions": sorted(list(functions))
    }


def reset_coverage_counters(build_dir: Path) -> None:
    """Reset coverage counters using fastcov --zerocounters"""
    subprocess.run([
        "fastcov", "--zerocounters", "--search-directory", str(build_dir),
        "--exclude", "/usr/include/*", "--exclude", "*/deps/*"
    ], cwd=build_dir.parent, capture_output=True, text=True, check=False)


def extract_coverage_data(build_dir: Path, test_name: str, demangle_cache: Dict[str, str]) -> Optional[Dict]:
    """Run fastcov for the just-executed test and parse its output"""
    # Sanitize test name for filename (handles both / and \ path separators)
    safe_name = test_name.replace('/', '_').replace('\\', '_')
    fastcov_output = build_dir / f"fastcov_{safe_name}.json"

    result = subprocess.run([
        "fastcov", "--gcov", "gcov", "--search-directory", str(build_dir),
        "--output", str(fastcov_output), "--exclude", "/usr/include/*",
        "--exclude", "*/deps/*", "--jobs", "4"
    ], cwd=build_dir.parent, capture_output=True, text=True, check=False)

    if result.returncode != 0:
        return None

    result_data = parse_fastcov_json(fastcov_output, test_name, demangle_cache)

    try:
        fastcov_output.unlink()
    except Exception:
        pass

    return result_data


def calculate_jobs(total_tests: int, target_jobs: int, max_job_time_minutes: int,
                    buffer_minutes: int, avg_test_time_seconds: float) -> Tuple[int, int]:
    """Calculate optimal number of jobs and tests per job for generate_matrix.py."""
    available_time_seconds = (max_job_time_minutes - buffer_minutes) * 60
    max_tests_per_job = int(available_time_seconds / avg_test_time_seconds)
    min_jobs = (total_tests + max_tests_per_job - 1) // max_tests_per_job

    # Try target_jobs, increase if needed
    total_jobs = target_jobs
    while True:
        tests_per_job = max(1, (total_tests + total_jobs - 1) // total_jobs)
        estimated_minutes = (tests_per_job * avg_test_time_seconds + buffer_minutes * 60) / 60.0

        if estimated_minutes <= max_job_time_minutes:
            break

        if total_jobs >= min_jobs:
            total_jobs = min_jobs
            tests_per_job = max(1, (total_tests + total_jobs - 1) // total_jobs)
            break

        total_jobs += 1

    return total_jobs, tests_per_job

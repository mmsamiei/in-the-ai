"""Provider-neutral generate(prompt, schema) interface. See docs/architecture.md."""
import json
import os
from pathlib import Path
import subprocess
from config import setting

from codex_runner import generate as codex_generate

ROOT = Path(__file__).resolve().parent


def generate(prompt, schema, config_path=None):
    path = Path(config_path) if config_path else ROOT / 'inference.json'
    config = json.loads(path.read_text())
    timeout = config.get('timeout_seconds', 240)
    if type(timeout) is not int or timeout < 1:
        raise ValueError('timeout_seconds must be a positive integer')
    backend = config.get('backend', 'codex')
    if backend == 'codex':
        return codex_generate(prompt, schema, timeout=timeout,
                              model=config.get('model'), reasoning_effort=config.get('reasoning_effort'))
    if backend != 'command':
        raise ValueError('Unknown inference backend')
    command = config.get('command')
    if not isinstance(command, list) or not command or not all(isinstance(arg, str) and arg for arg in command):
        raise ValueError('command must be a nonempty argv list; shell strings are not accepted')
    pass_env = config.get('pass_env', [])
    if not isinstance(pass_env, list) or not all(isinstance(key, str) for key in pass_env):
        raise ValueError('pass_env must be a list of environment variable names')
    environment = {key: value for key, value in os.environ.items() if key in {
        'PATH', 'HOME', 'LANG', 'LC_ALL', 'TMPDIR', 'SSL_CERT_FILE', 'SSL_CERT_DIR',
        'HTTPS_PROXY', 'HTTP_PROXY', 'NO_PROXY', *pass_env}}
    for key in pass_env:
        value = setting(key)
        if value is not None:
            environment[key] = value
    request = dict(protocol_version=1, prompt=prompt, schema=schema)
    try:
        completed = subprocess.run(command, input=json.dumps(request, ensure_ascii=False),
                                   text=True, capture_output=True, timeout=timeout,
                                   cwd=ROOT, env=environment)
    except subprocess.TimeoutExpired:
        raise RuntimeError('Inference command timed out') from None
    if completed.returncode:
        # Custom adapters may log credentials on stderr. Never persist raw logs.
        raise RuntimeError(f'Inference command failed with exit code {completed.returncode}')
    try:
        result = json.loads(completed.stdout)
    except ValueError:
        raise ValueError('Inference command must write one JSON object to stdout') from None
    if not isinstance(result, dict):
        raise ValueError('Inference command must return a JSON object')
    return result

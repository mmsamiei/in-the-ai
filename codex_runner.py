"""One isolated, non-interactive Codex call with structured final output."""
import json
import os
from pathlib import Path
import subprocess
import tempfile


def generate(prompt, schema, timeout=240, model=None, reasoning_effort=None):
    if model is not None and (not isinstance(model, str) or not model.strip()):
        raise ValueError('model must be a nonempty string')
    if reasoning_effort is not None and reasoning_effort not in ('none', 'low', 'medium', 'high', 'xhigh', 'max'):
        raise ValueError('Unsupported reasoning_effort; Light maps to low')
    with tempfile.TemporaryDirectory(prefix='ai-news-inference-') as directory:
        root = Path(directory)
        schema_path = root / 'schema.json'
        output = root / 'result.json'
        schema_path.write_text(json.dumps(schema))
        command = ['codex', '--no-daemon', '-a', 'never', 'exec',
                   '--ignore-user-config', '--ephemeral', '--skip-git-repo-check',
                   '--sandbox', 'read-only', '--cd', directory,
                   '--disable', 'shell_tool', '--disable', 'apps', '--disable', 'plugins',
                   '--disable', 'hooks', '--disable', 'computer_use', '--disable', 'browser_use',
                   '-c', 'web_search="disabled"',
                   '--output-schema', str(schema_path), '--output-last-message', str(output)]
        if model:
            command.extend(['--model', model])
        if reasoning_effort:
            command.extend(['-c', 'model_reasoning_effort=' + json.dumps(reasoning_effort)])
        command.append('-')
        # No Telegram or other application secrets are passed to inference.
        env = {key: value for key, value in os.environ.items()
               if key in ('PATH', 'HOME', 'CODEX_HOME', 'LANG', 'LC_ALL', 'TMPDIR',
                          'SSL_CERT_FILE', 'SSL_CERT_DIR', 'HTTPS_PROXY', 'HTTP_PROXY', 'NO_PROXY')}
        completed = subprocess.run(command, input=prompt, text=True, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, env=env, timeout=timeout)
        if completed.returncode or not output.exists():
            detail = completed.stderr[-2500:]
            raise RuntimeError(f'Codex failed ({completed.returncode}): {detail}')
        return json.loads(output.read_text())

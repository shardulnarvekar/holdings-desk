"""One-time local setup. Uses only Python's standard library; never reads an API key."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parent


def main():
    if sys.version_info < (3, 12):
        print('Pinned dependencies require Python 3.12 or newer. Use Python 3.13 (tested).')
        print('On Windows: py -3.13 setup_project.py')
        return 1
    environment = ROOT / '.venv'
    executable = environment / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    try:
        if executable.exists():
            version = subprocess.run(
                [str(executable), '-c', 'import sys; print("%d.%d" % sys.version_info[:2])'],
                check=True, capture_output=True, text=True,
            ).stdout.strip()
            if tuple(map(int, version.split('.'))) < (3, 12):
                print(f'Existing .venv uses Python {version}, which cannot install the pinned dependencies.')
                print('Rename .venv to .venv-old, then rerun setup using Python 3.13.')
                print('Your .env file should stay in the project folder.')
                return 1
        if not executable.exists():
            print('Creating the project virtual environment...', flush=True)
            venv.EnvBuilder(with_pip=True).create(environment)
        print('Installing pinned dependencies...', flush=True)
        subprocess.run([str(executable), '-m', 'pip', 'install', '-r', str(ROOT / 'requirements-lock.txt')], check=True)
        subprocess.run([str(executable), '-m', 'pip', 'check'], check=True)
        if not (ROOT / '.env').exists():
            shutil.copyfile(ROOT / '.env.example', ROOT / '.env')
        print('\nSetup complete. Your existing .env, if any, was preserved.')
        print('Next: open .env, set GEMINI_API_KEY, and save it.')
        command = r'.\.venv\Scripts\python.exe' if os.name == 'nt' else './.venv/bin/python'
        print(f'CLI: {command} -m portfolio_agent')
        print(f'Optional UI: {command} -m streamlit run app.py')
        return 0
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f'Setup failed: {exc}', file=sys.stderr)
        print('Check your Python installation and internet access, then rerun this command.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

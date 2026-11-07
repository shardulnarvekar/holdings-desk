"""Catch unsupported interpreters before attempting dependency installation."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import setup_project


def test_python_310_is_rejected_before_creating_environment(monkeypatch, tmp_path):
    monkeypatch.setattr(setup_project, 'ROOT', tmp_path)
    monkeypatch.setattr(setup_project.sys, 'version_info', (3, 10, 9))
    run = Mock()
    monkeypatch.setattr(setup_project.subprocess, 'run', run)
    assert setup_project.main() == 1
    assert not (tmp_path / '.venv').exists()
    run.assert_not_called()


def test_old_environment_is_rejected_even_with_new_python(monkeypatch, tmp_path):
    monkeypatch.setattr(setup_project, 'ROOT', tmp_path)
    monkeypatch.setattr(setup_project.sys, 'version_info', (3, 13, 0))
    executable = tmp_path / '.venv' / ('Scripts/python.exe' if setup_project.os.name == 'nt' else 'bin/python')
    executable.parent.mkdir(parents=True)
    executable.touch()
    run = Mock(return_value=SimpleNamespace(stdout='3.10\n'))
    monkeypatch.setattr(setup_project.subprocess, 'run', run)
    assert setup_project.main() == 1
    assert run.call_count == 1
    assert executable.exists()


@pytest.mark.parametrize("version", ["3.11", "3.12", "3.13"])
def test_supported_environment_preserves_key_file(monkeypatch, tmp_path, version):
    monkeypatch.setattr(setup_project, 'ROOT', tmp_path)
    monkeypatch.setattr(setup_project.sys, 'version_info', (3, 13, 0))
    executable = tmp_path / '.venv' / ('Scripts/python.exe' if setup_project.os.name == 'nt' else 'bin/python')
    executable.parent.mkdir(parents=True)
    executable.touch()
    env = tmp_path / '.env'
    env.write_text('GEMINI_API_KEY=local-placeholder', encoding='utf-8')
    run = Mock(return_value=SimpleNamespace(stdout=version+'\n'))
    monkeypatch.setattr(setup_project.subprocess, 'run', run)
    assert setup_project.main() == 0
    assert run.call_count == 3
    assert env.read_text(encoding='utf-8') == 'GEMINI_API_KEY=local-placeholder'

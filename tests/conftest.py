"""Fixtures compartilhadas de todo o pacote de testes.

`Settings` (T3) exige `ORCHESTRATOR_API_KEY`/`OPENROUTER_API_KEY`/`OPENROUTER_MODEL` sem
default -- `create_app()` (T14) passou a resolvê-las via `api.auth.get_settings()` dentro do
`lifespan` a partir de T25 (construção do grafo). `setdefault` preserva qualquer valor real já
presente no ambiente do desenvolvedor e só preenche os testes que não fornecem o próprio
override (ex.: `tests/unit/test_settings.py`, que limpa e resseta essas mesmas chaves por
teste via `monkeypatch`).
"""

import os

os.environ.setdefault("ORCHESTRATOR_API_KEY", "test-api-key")
os.environ.setdefault("OPENROUTER_API_KEY", "test-openrouter-key")
os.environ.setdefault("OPENROUTER_MODEL", "test/model")

"""Import sentence-transformers without tripping a native library conflict.

## The problem

On this project's Windows environment, `import sentence_transformers` crashes
the interpreter outright - a Windows access violation, not a Python exception,
so it cannot be caught. The faulting frame is pyarrow's native extension, loaded
indirectly: sentence_transformers imports datasets, datasets imports pyarrow.

What makes it a load-order conflict rather than a broken package is that every
explicit ordering works. `import pyarrow` alone is fine. So is
`import torch, transformers, pyarrow`. Only the order sentence_transformers
happens to use internally crashes, and importing pyarrow first makes it work
every time.

## The workaround

Import pyarrow before sentence_transformers, so its native library is loaded
into a clean process rather than after whatever conflicts with it.

This is a local environment quirk, not a property of the libraries, which is why
it lives in one guarded place with an explanation instead of being sprinkled
through the retrieval modules as an unexplained import. If pyarrow is absent the
pre-import is skipped: it is a workaround, not a dependency.
"""

from __future__ import annotations


def _preload_pyarrow() -> None:
    try:
        import pyarrow  # noqa: F401
    except Exception:  # pragma: no cover - absent or already broken; try anyway
        pass


def load_sentence_transformer():
    _preload_pyarrow()
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer


def load_cross_encoder():
    _preload_pyarrow()
    from sentence_transformers import CrossEncoder

    return CrossEncoder

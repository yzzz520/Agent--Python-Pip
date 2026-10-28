"""Backend service for the pip failure attribution dataset.

The package only *reads* the artifacts produced by the offline pipeline
(``requirements_all/``, ``error_all/``, ``reports_*_all/``, ``golden_labels.json``,
``recovered/``) and exposes them through an HTTP API with a relational schema.
Nothing here rewrites those artifacts unless a job is explicitly requested.
"""

__version__ = "1.0.0"

from .config import ScannerConfig
from .models import (
    GroupedCandidateSummary,
    PatternCandidate,
    RunMetadata,
    ScanRunSummary,
    SymbolContext,
)


def _missing_report_dependency(*_args, **_kwargs):
    raise ModuleNotFoundError('jinja2 is required for scripts.oneil_scanner report helpers')


try:
    from .report import write_csv, write_html, write_json, write_report_bundle
except ModuleNotFoundError as exc:
    if exc.name != 'jinja2':
        raise
    write_csv = _missing_report_dependency
    write_html = _missing_report_dependency
    write_json = _missing_report_dependency
    write_report_bundle = _missing_report_dependency

__all__ = [
    'GroupedCandidateSummary',
    'PatternCandidate',
    'RunMetadata',
    'ScanRunSummary',
    'ScannerConfig',
    'SymbolContext',
    'write_csv',
    'write_html',
    'write_json',
    'write_report_bundle',
]

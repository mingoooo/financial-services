from __future__ import annotations

from scripts.oneil_scanner.models import ScannerConfig
from scripts.scan_oneil_setups import build_config, build_parser


def test_qullamaggie_config_default_profile_remains_oneil() -> None:
    config = build_config(build_parser().parse_args([]))

    assert config.strategy_profile == 'oneil'


def test_qullamaggie_config_parser_accepts_profile_option() -> None:
    args = build_parser().parse_args(['--strategy-profile', 'qullamaggie'])

    assert args.strategy_profile == 'qullamaggie'


def test_qullamaggie_config_build_sets_scanner_profile() -> None:
    config = build_config(build_parser().parse_args(['--strategy-profile', 'qullamaggie']))

    assert isinstance(config, ScannerConfig)
    assert config.strategy_profile == 'qullamaggie'

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from scripts.notify_telegram_market_report import build_message, main


class NotifyTelegramMarketReportTests(unittest.TestCase):
    def test_build_message_for_premarket_reads_markdown_title(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_path = Path(tmp_dir) / 'REPORT.md'
            report_path.write_text('# 自定义盘前报告\n\n内容', encoding='utf-8')

            message = build_message(
                family='premarket',
                report_path=str(report_path),
                pages_url='https://example.test/premarket/index.html',
                run_label='manual check',
            )

        self.assertIn('自定义盘前报告', message)
        self.assertIn('发送时点: manual check', message)
        self.assertIn('盘前报告已生成。', message)
        self.assertIn('报告页面: https://example.test/premarket/index.html', message)

    def test_build_message_for_oneil_reads_json_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_path = Path(tmp_dir) / 'live-full-latest.json'
            report_path.write_text(
                json.dumps(
                    {
                        'run_metadata': {
                            'run_timestamp': '2026-07-29T14:45:00Z',
                            'report_name': 'live-full-latest',
                            'warnings': ['Data source lagged for one symbol.'],
                        },
                        'universe': 'oneil-candidates-live-full',
                        'candidate_count': 2,
                        'candidates': [
                            {
                                'symbol': 'NVDA',
                                'pattern_variant': 'vcp_breakout',
                                'trigger_date': '2026-07-29',
                                'setup_score': 92.5,
                            },
                            {
                                'symbol': 'PLTR',
                                'pattern_type': 'event_driven',
                                'trigger_date': '2026-07-28',
                            },
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding='utf-8',
            )

            message = build_message(
                family='oneil',
                report_path=str(report_path),
                pages_url='https://example.test/oneil/index.html',
                run_label="O'Neil scheduled",
            )

        self.assertIn("O'Neil 实时扫描", message)
        self.assertIn("发送时点: O'Neil scheduled", message)
        self.assertIn('报告: live-full-latest', message)
        self.assertIn('运行时间: 2026-07-29T14:45:00Z', message)
        self.assertIn('股票池: oneil-candidates-live-full', message)
        self.assertIn('候选数量: 2', message)
        self.assertIn('- NVDA vcp_breakout | Trigger 2026-07-29 | Score 92.5', message)
        self.assertIn('- PLTR event_driven | Trigger 2026-07-28', message)
        self.assertIn('注意事项: Data source lagged for one symbol.', message)
        self.assertIn('报告页面: https://example.test/oneil/index.html', message)

    def test_build_message_for_qullamaggie_reads_json_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_path = Path(tmp_dir) / 'live-full-latest.json'
            report_path.write_text(
                json.dumps(
                    {
                        'run_metadata': {
                            'run_timestamp': '2026-08-07T10:40:00Z',
                            'report_name': 'live-full-latest',
                        },
                        'universe': 'all-us',
                        'candidate_count': 1,
                        'candidates': [
                            {
                                'symbol': 'VAC',
                                'pattern_variant': 'earnings-gap',
                                'trigger_date': '2026-08-06',
                                'setup_score': 97.9,
                            },
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding='utf-8',
            )

            message = build_message(
                family='qullamaggie',
                report_path=str(report_path),
                pages_url='https://example.test/qullamaggie/index.html',
                run_label='Q scheduled',
            )

        self.assertIn('Qullamaggie 实时扫描', message)
        self.assertIn('候选数量: 1', message)
        self.assertIn('- VAC earnings-gap | Trigger 2026-08-06 | Score 97.9', message)
        self.assertIn('报告页面: https://example.test/qullamaggie/index.html', message)

    def test_build_message_for_full_includes_qullamaggie_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            premarket_report = tmp_root / 'REPORT.md'
            premarket_report.write_text('# Full Run Premarket\n', encoding='utf-8')
            oneil_report = tmp_root / 'oneil.json'
            oneil_report.write_text(json.dumps({'run_metadata': {'run_timestamp': '2026-08-07T10:40:00Z'}, 'universe': 'all-us', 'candidate_count': 0, 'candidates': []}, ensure_ascii=False), encoding='utf-8')
            qullamaggie_report = tmp_root / 'qullamaggie.json'
            qullamaggie_report.write_text(json.dumps({'run_metadata': {'run_timestamp': '2026-08-07T10:40:00Z'}, 'universe': 'all-us', 'candidate_count': 1, 'candidates': [{'symbol': 'VAC', 'pattern_variant': 'earnings-gap', 'trigger_date': '2026-08-06'}]}, ensure_ascii=False), encoding='utf-8')

            message = build_message(
                family='full',
                report_path=None,
                pages_url=None,
                run_label='full run',
                premarket_report_path=str(premarket_report),
                oneil_report_path=str(oneil_report),
                qullamaggie_report_path=str(qullamaggie_report),
                oneil_pages_url='https://example.test/oneil/index.html',
                qullamaggie_pages_url='https://example.test/qullamaggie/index.html',
            )

        self.assertIn('Qullamaggie 候选数量: 1', message)
        self.assertIn('Qullamaggie 报告: https://example.test/qullamaggie/index.html', message)

    def test_build_message_omits_pages_url_when_not_provided(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_path = Path(tmp_dir) / 'REPORT.md'
            report_path.write_text('# 无链接盘前报告\n', encoding='utf-8')

            message = build_message(
                family='premarket',
                report_path=str(report_path),
                pages_url=None,
                run_label='scheduled 10:00 ET',
            )

        self.assertIn('无链接盘前报告', message)
        self.assertNotIn('报告页面:', message)

    def test_main_returns_error_for_oneil_malformed_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_path = Path(tmp_dir) / 'live-full-latest.json'
            report_path.write_text('{not valid json', encoding='utf-8')

            stderr = io.StringIO()
            with redirect_stderr(stderr):
                exit_code = main(['--family', 'oneil', '--report-path', str(report_path), '--dry-run'])

        self.assertEqual(exit_code, 1)
        self.assertIn('Failed to build Telegram notification', stderr.getvalue())

    @patch('scripts.notify_telegram_market_report._send_telegram')
    def test_main_skips_send_when_secrets_missing(self, send_telegram) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_path = Path(tmp_dir) / 'REPORT.md'
            report_path.write_text('# Missing Secrets Premarket\n', encoding='utf-8')

            stderr = io.StringIO()
            with patch.dict('os.environ', {}, clear=True):
                with redirect_stderr(stderr):
                    exit_code = main(['--family', 'premarket', '--report-path', str(report_path)])

        self.assertEqual(exit_code, 0)
        send_telegram.assert_not_called()
        self.assertIn('TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID missing, skip notification.', stderr.getvalue())

    def test_main_dry_run_supports_both_families_without_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            premarket_report = tmp_root / 'REPORT.md'
            premarket_report.write_text('# Dry Run Premarket\n', encoding='utf-8')
            oneil_report = tmp_root / 'live-full-latest.json'
            oneil_report.write_text(
                json.dumps(
                    {
                        'run_metadata': {
                            'run_timestamp': '2026-07-29T14:45:00Z',
                            'report_name': 'live-full-latest',
                        },
                        'universe': 'oneil-candidates-live-full',
                        'candidates': [],
                    },
                    ensure_ascii=False,
                ),
                encoding='utf-8',
            )

            premarket_stdout = io.StringIO()
            with redirect_stdout(premarket_stdout):
                premarket_exit = main(['--family', 'premarket', '--report-path', str(premarket_report), '--dry-run'])

            oneil_stdout = io.StringIO()
            with redirect_stdout(oneil_stdout):
                oneil_exit = main(['--family', 'oneil', '--report-path', str(oneil_report), '--dry-run'])

            qullamaggie_stdout = io.StringIO()
            with redirect_stdout(qullamaggie_stdout):
                qullamaggie_exit = main(['--family', 'qullamaggie', '--report-path', str(oneil_report), '--dry-run'])

        self.assertEqual(premarket_exit, 0)
        self.assertIn('Dry Run Premarket', premarket_stdout.getvalue())
        self.assertEqual(oneil_exit, 0)
        self.assertIn("O'Neil 实时扫描", oneil_stdout.getvalue())
        self.assertIn('当前没有命中候选。', oneil_stdout.getvalue())
        self.assertEqual(qullamaggie_exit, 0)
        self.assertIn('Qullamaggie 实时扫描', qullamaggie_stdout.getvalue())


if __name__ == '__main__':
    unittest.main()

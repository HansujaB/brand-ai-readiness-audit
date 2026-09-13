#!/usr/bin/env python3
"""Validate an owner report; optionally repair counts and assign IDs to reviewed findings."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import jsonschema
from auditlib.runner import atomic_json
from auditlib.reporting import priority_summary


def validate(report, repair=False):
    if repair:
        for i, finding in enumerate(report['findings'], 1):
            finding['id'] = f'F-{i:03d}'
        report['summary'] = priority_summary(report['findings'], 'severity', 'total_findings')
        report['improvements_summary'] = priority_summary(report.get('improvements', []), 'priority', 'total_improvements')
    schema = json.loads((Path(__file__).resolve().parents[1] / 'references/owner.schema.json').read_text(encoding='utf-8'))
    jsonschema.validate(report, schema)
    expected = {'total_findings':len(report['findings']),
        **{s:sum(f['severity'] == s for f in report['findings']) for s in ('critical','high','medium','low')}}
    if any(report['summary'].get(key, 0 if key == 'low' else None) != value for key,value in expected.items()):
        raise ValueError('Summary counts do not match findings; use --write to recompute them.')
    expected_improvements = priority_summary(report.get('improvements', []), 'priority', 'total_improvements')
    if report['improvements_summary'] != expected_improvements:
        raise ValueError('Improvement counts do not match listed improvements; use --write to recompute them.')
    if len({f['id'] for f in report['findings']}) != len(report['findings']):
        raise ValueError('Duplicate finding IDs; merge duplicate evidence before finalizing.')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', help='Company report to validate, e.g. lifestyle_report.json')
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    report = validate(json.loads(Path(args.report).read_text(encoding='utf-8-sig')), repair=args.write)
    if args.write:
        atomic_json(args.report, report)
    print('Valid owner report: ' + str(len(report['findings'])) + ' findings.')


if __name__ == '__main__':
    main()

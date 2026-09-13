"""Supervisor integration: stop a genuinely hung owned worker and retain JSON."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
ROOT=Path(__file__).resolve().parents[1]


class SupervisorTests(unittest.TestCase):
    def test_hung_worker_is_stopped_and_partial_report_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            script=Path(temp)/'hung_worker.py'
            script.write_text('import sys,time\nfrom pathlib import Path\nsys.path.insert(0,'+repr(str(ROOT))+')\nfrom auditlib.runner import main, parse_args, snapshot, atomic_json\nfrom auditlib.collection import Collector\nfrom auditlib.diagnostics import Results\na=parse_args()\nif a._worker:\n    atomic_json(a._worker,snapshot(a.site_url,a.brand,Collector(),Results(),[],{},a.budget))\n    time.sleep(60)\nelse:\n    main()\n',encoding='utf-8')
            started=time.monotonic()
            destination=Path(temp)/'output'
            destination.mkdir()
            process=subprocess.run([sys.executable,str(script),'https://example.com/','--budget','1'],cwd=destination,capture_output=True,text=True,timeout=25)
            self.assertEqual(process.returncode,0,process.stderr)
            self.assertIn('Saved example_report.json',process.stdout)
            self.assertEqual([p.name for p in destination.iterdir()],['example_report.json'])
            report=json.loads((destination/'example_report.json').read_text(encoding='utf-8'))
            self.assertLess(time.monotonic()-started,23)
            self.assertIn('could not be assessed',report['note'])
            self.assertEqual(report['findings'],[])
            self.assertEqual(set(report),{'site','audited_at','summary','improvements_summary','findings','note'})

    def test_cleanup_failure_and_bad_checkpoint_still_emit_partial_json(self):
        import contextlib
        import io
        from unittest.mock import patch, MagicMock
        sys.path.insert(0,str(ROOT))
        from auditlib.runner import main
        child=MagicMock(pid=12345,returncode=None)
        child.communicate.side_effect=[subprocess.TimeoutExpired('worker',1),subprocess.TimeoutExpired('worker',1)]
        child.kill.side_effect=OSError('cleanup failed')
        def launch(command, **kwargs):
            Path(command[-1]).write_text('{corrupt',encoding='utf-8')
            return child
        output=io.StringIO()
        with patch.object(sys,'argv',['runner.py','https://example.com/','--budget','1']), patch('auditlib.runner.subprocess.Popen',side_effect=launch), patch('auditlib.runner.subprocess.run',side_effect=OSError('tree cleanup failed')), patch('auditlib.runner.os.killpg',create=True,side_effect=OSError('tree cleanup failed')), patch('auditlib.runner.atomic_json') as save, contextlib.redirect_stdout(output):
            main()
        save.assert_called_once()
        self.assertEqual(save.call_args.args[0],'example_report.json')
        report=save.call_args.args[1]
        self.assertIn('could not be assessed',report['note'])
        self.assertEqual(report['summary']['total_findings'],0)
        child.kill.assert_called_once()
        child.stderr.close.assert_called_once()


if __name__=='__main__':
    unittest.main()

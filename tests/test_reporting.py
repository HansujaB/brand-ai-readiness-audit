"""Business report contract and the single-file CLI output."""
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import jsonschema
from test_audit import SITE, collector, response, page
from auditlib.diagnostics import Results
from auditlib.reporting import owner_report, report_filename, priority_summary
from auditlib.runner import parse_args, audit
from auditlib.identity import published_brand

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT/'skills/audit-orchestrator/references/owner.schema.json').read_text(encoding='utf-8'))


class BusinessReportTests(unittest.TestCase):
    def report(self, results):
        return {'site':SITE,'audited_at':'2026-09-20T14:32:00Z','findings':results.findings,
            'checks':results.checks,'proactive_suggestions':results.suggestions,
            'run_metadata':{'pages_audited':[SITE],'request_log':[{'url':SITE}]*500},
            'fact_extraction_tests':[{'internal':'details'}]*500,'review_queue':[]}

    def test_contest_minimum_needs_no_diagnostic_fields(self):
        report={'site':'example.com','audited_at':'2026-09-20T14:32:00Z',
            'summary':{'total_findings':1,'critical':0,'high':1,'medium':0},
            'improvements_summary':priority_summary([], 'priority', 'total_improvements'),
            'findings':[{'id':'F-001','title':'Product information cannot be extracted',
                'severity':'high','evidence':'The product description is only available as an image.',
                'suggested_action':{'summary':'Publish the product description as readable text.','priority':'high'}}]}
        spec=importlib.util.spec_from_file_location('report_validator',ROOT/'skills/audit-orchestrator/scripts/validate_report.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        module.validate(report)
        report['coverage']={}
        with self.assertRaises(jsonschema.ValidationError):
            module.validate(report)

    def test_internal_details_do_not_leak_into_business_report(self):
        results=Results()
        results.finding('content.example',SITE,'Missing product information',
            'A relevant condition is separated from the product price. '*100,
            'Place the condition beside the product price.','Inspect the source again.')
        report=owner_report(self.report(results))
        jsonschema.validate(report,SCHEMA)
        self.assertEqual(set(report),{'site','audited_at','summary','improvements_summary','findings'})
        self.assertLess(len(json.dumps(report,indent=2).splitlines()),50)
        self.assertLessEqual(len(report['findings'][0]['evidence']),400)
        self.assertEqual(set(report['findings'][0]['suggested_action']),{'summary','priority','verification'})
        self.assertEqual(report['findings'][0]['suggested_action']['verification'],'Inspect the source again.')

    def test_same_fix_groups_pages_but_distinct_entities_remain_separate(self):
        results=Results()
        for url,entity in [(SITE+'a','Plan A'),(SITE+'b','Plan A'),(SITE+'c','Plan B')]:
            results.finding('facts.context_loss',url,'Billing condition separated',
                'Annual commitment is separated from the monthly price.',
                'Show the billing commitment beside the price.','Inspect the price.',entity=entity)
        report=owner_report(self.report(results))
        self.assertEqual(report['summary']['total_findings'],2)
        self.assertEqual(report['findings'][0]['pages'],[SITE+'a',SITE+'b'])
        self.assertEqual(report['findings'][1]['pages'],[SITE+'c'])
        self.assertEqual([f['id'] for f in report['findings']],['F-001','F-002'])

    def test_cli_rejects_additional_output_options(self):
        for option in ('--output','--diagnostics-output'):
            with self.subTest(option=option),patch('sys.stderr',new=io.StringIO()),self.assertRaises(SystemExit):
                parse_args([SITE,option,'extra.json'])

    def test_company_filenames_use_brand_or_domain_and_stay_in_output_directory(self):
        cases=[('https://www.ikea.com/in/en/','IKEA','ikea_report.json'),
               ('https://www.lifestylestores.com/in/en/','Lifestyle','lifestyle_report.json'),
               ('https://shop.example.co.in/',None,'example_report.json'),
               (SITE,'Acme & Sons','acme_sons_report.json'),
               (SITE,'../../IKEA','ikea_report.json'),
               (SITE,'   ','example_report.json')]
        for site,brand,expected in cases:
            with self.subTest(site=site,brand=brand):
                self.assertEqual(report_filename(site,brand),expected)

    def test_explicit_brand_overrides_published_site_name(self):
        html='<meta property="og:site_name" content="Lifestyle"><main>Shop</main>'
        c=collector({SITE+'robots.txt':response(''),SITE:response(html)})
        report=audit(SITE,brand='Chosen Name',collector=c,browser=False)
        self.assertEqual(report['brand'],'Chosen Name')
        self.assertEqual(report_filename(SITE,report['brand']),'chosen_name_report.json')
        self.assertEqual(published_brand(page('<script type="application/ld+json">{"@type":"WebSite","name":"IKEA"}</script>')),'IKEA')

    def test_improvement_counts_are_independent_and_validator_repairs_them(self):
        results=Results()
        results.finding('content.issue',SITE,'Issue','Observed issue','Fix the issue','Check the fix.',severity='high')
        for i,priority in enumerate(('medium','medium','low')):
            results.suggest('content.'+str(i),SITE,'Observed opportunity','Improve item '+str(i),'Verify item '+str(i),priority=priority)
        report=owner_report(self.report(results))
        self.assertEqual(report['summary']['high'],1)
        self.assertEqual(report['improvements_summary'],{'total_improvements':3,'critical':0,'high':0,'medium':2,'low':1})
        self.assertTrue(all(i['verification'].startswith('Verify item') for i in report['improvements']))
        spec=importlib.util.spec_from_file_location('report_validator',ROOT/'skills/audit-orchestrator/scripts/validate_report.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        report['improvements_summary']['high']=9
        with self.assertRaises(ValueError):module.validate(report)
        module.validate(report,repair=True)
        self.assertEqual(report['improvements_summary']['high'],0)
        self.assertEqual(report['summary']['total_findings'],1)

    def test_successful_cli_uses_published_company_name_for_its_only_report(self):
        with tempfile.TemporaryDirectory() as temp:
            script=Path(temp)/'offline_audit.py'
            script.write_text('''import sys
sys.path.insert(0,ROOT)
import auditlib.runner as runner
from auditlib.collection import Collector, normalize
def transport(url):
    body = b'<html lang="en"><meta property="og:site_name" content="Lifestyle"><main><h1>Furniture shop</h1></main></html>' if url == 'https://example.com/' else b''
    status = 200 if url in ('https://example.com/','https://example.com/robots.txt') else 404
    return {'status':status,'headers':{'content-type':'text/html'},'body':body}
runner.Collector = lambda **kwargs: Collector(transport=transport,validator=normalize,**kwargs)
runner.main()
'''.replace('ROOT',repr(str(ROOT))),encoding='utf-8')
            destination=Path(temp)/'output';destination.mkdir()
            process=subprocess.run([sys.executable,str(script),SITE,'--no-browser','--budget','10'],
                cwd=destination,capture_output=True,text=True,timeout=25)
            self.assertEqual(process.returncode,0,process.stderr)
            self.assertEqual([p.name for p in destination.iterdir()],['lifestyle_report.json'])
            report=json.loads((destination/'lifestyle_report.json').read_text(encoding='utf-8'))
            jsonschema.validate(report,SCHEMA)
            self.assertEqual(report['site'],SITE)
            self.assertNotIn('coverage',report)
            self.assertEqual(len(process.stdout.splitlines()),1)


if __name__=='__main__':
    unittest.main()

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import china_research as research


class ChinaPolicyResearchTests(unittest.TestCase):
    def files(self):
        source={'dns':{'enable':True,'nameserver':['rcode://success']},
                'proxy-groups':[{'name':name,'type':'select','proxies':['DIRECT']} for name in ['PROXY','HKMTMedia','Final']],
                'proxies':[], 'rule-providers':{'rpi-local-proxy':{'type':'file','behavior':'classical','format':'text','path':'/etc/nikki/run/rpi-rules/proxy.list'}},
                'rules':['RULE-SET,rpi-local-proxy,PROXY','DOMAIN-SUFFIX,bilibili.com,HKMTMedia','DOMAIN-SUFFIX,qq.com,DIRECT','MATCH,Final']}
        runtime=copy.deepcopy(source);runtime['dns'].update({'enhanced-mode':'fake-ip','listen':'127.0.0.1:1053','fake-ip-range':'198.18.0.1/16','direct-nameserver-follow-policy':False})
        targets=[{'url':'https://www.xiaohongshu.com/','expected_status':[200,302],'pilot':True}]
        dns=[{'host':'www.xiaohongshu.com','resolver':r,'outcome':'answers','addresses':[{'baseline':'8.8.8.8','alidns':'1.1.1.1','dnspod':'9.9.9.9'}[r]],'rcode':'NOERROR'} for r in ['baseline','alidns','dnspod']]
        samples=[]
        for resolver,latency in [('baseline',.8),('alidns',.2),('dnspod',.3)]:
            for vantage in ['pi','client']:
                for index in range(5):
                    value=latency if vantage=='pi' else 2.0
                    samples.append({'host':'www.xiaohongshu.com','resolver':resolver,'vantage':vantage,'ip':{'baseline':'8.8.8.8','alidns':'1.1.1.1','dnspod':'9.9.9.9'}[resolver],'sample':index,'success':True,'exitcode':0,'ssl_verify_result':0,'http_code':302,'redirect_same_origin':True,'time_starttransfer':value,'time_total':value+.1})
        files={'source.yaml':research.encode(source),'runtime.yaml':research.encode(runtime),'proxy.list':b'DOMAIN,sefapplyap.sef.org.tw\n',
               'targets.json':research.encode(targets),'dns.json':research.encode(dns),'samples.json':research.encode(samples),'core-version.json':research.encode({'version':'v1.19.27'}),
               'selectors-before.json':research.encode({'HKMTMedia':'DIRECT'}),'selectors-after.json':research.encode({'HKMTMedia':'DIRECT'})}
        state={'source_sha256':research.sha(files['source.yaml']),'runtime_sha256':research.sha(files['runtime.yaml']),'provider_sha256':research.sha(files['proxy.list'])}
        files['state-before.json']=research.encode(state);files['state-after.json']=research.encode(state)
        return files

    def manifest(self,files):
        return {'schema':research.SCHEMA,'state_stable':True,'sampling_complete':True,'sample_count':5,'vantages':['pi','client'],'files':{n:{'sha256':research.sha(v),'bytes':len(v)} for n,v in files.items()}}

    def test_composer_preserves_special_policies_source_and_effective_overrides(self):
        files=self.files();base=json.loads(files['source.yaml'])
        candidate,data,review=research.compose(files,'alidns',['+.xiaohongshu.com'])
        self.assertEqual(candidate['rules'][:-2],base['rules'][:-1])
        self.assertEqual(candidate['rules'][-1],base['rules'][-1])
        self.assertEqual(candidate['proxy-groups'][:-1],base['proxy-groups'])
        self.assertEqual(candidate['rule-providers']['rpi-local-proxy'],base['rule-providers']['rpi-local-proxy'])
        self.assertEqual(candidate['dns']['nameserver'],base['dns']['nameserver'])
        self.assertEqual(candidate['dns']['nameserver-policy']['rule-set:china-services-pilot'],
                         ['https://dns.alidns.com/dns-query#ChinaServices'])
        self.assertIn(b'www.xiaohongshu.com',data)
        self.assertFalse(review['deployable'])
        self.assertNotIn('ChinaServices',[x['name'] for x in base['proxy-groups']])

    def test_protected_media_and_legacy_direct_conflicts_are_not_overwritten(self):
        for host,rule in [('www.bilibili.com','+.bilibili.com'),('weixin.qq.com','+.qq.com')]:
            files=self.files();files['targets.json']=research.encode([{'url':'https://'+host+'/','expected_status':[200],'pilot':True}])
            with self.assertRaisesRegex(ValueError,'優先規則'):
                research.compose(files,'alidns',[rule])

    def test_ambiguous_dns_and_remote_provider_refused(self):
        for change in ['policy','effective','provider','name']:
            files=self.files();source=json.loads(files['source.yaml']);runtime=json.loads(files['runtime.yaml'])
            if change=='policy':
                source['dns']['nameserver-policy']={'example.com':['rcode://success']};runtime['dns']=copy.deepcopy(source['dns'])
            elif change=='effective':runtime['dns']['nameserver']=['https://unreviewed.example/']
            elif change=='provider':source['proxy-providers']={'foreign':{'type':'http'}}
            elif change=='name':source['proxy-groups'].append({'name':'ChinaServices','proxies':['DIRECT']})
            files['source.yaml']=research.encode(source);files['runtime.yaml']=research.encode(runtime)
            with self.subTest(change=change),self.assertRaises(ValueError):research.compose(files,'alidns',['+.xiaohongshu.com'])

    def test_baseline_fallback_keeps_original_dns(self):
        files=self.files();source=json.loads(files['source.yaml'])
        candidate,_,_=research.compose(files,'baseline',['+.xiaohongshu.com'])
        self.assertEqual(candidate['dns'],source['dns'])

    def test_report_does_not_mix_vantages_or_recommend_partial_state(self):
        files=self.files();manifest=self.manifest(files)
        report=research.summary(manifest,files)
        self.assertEqual(report['recommendations'][0]['candidate_to_review'],'alidns')
        client=[x for x in report['comparisons'] if x['vantage']=='client']
        self.assertTrue(all(x['median_ttfb']==2.0 for x in client))
        for key in ['state_stable','sampling_complete']:
            report=research.summary({**manifest,key:False},files)
            self.assertIsNone(report['recommendations'][0]['candidate_to_review'])

    def test_identical_cdn_answers_do_not_justify_resolver_switch(self):
        files=self.files()
        dns=json.loads(files['dns.json']);samples=json.loads(files['samples.json'])
        for answer in dns:answer['addresses']=['1.1.1.1']
        for sample in samples:sample['ip']='1.1.1.1'
        files['dns.json']=research.encode(dns);files['samples.json']=research.encode(samples)
        recommendation=research.summary(self.manifest(files),files)['recommendations'][0]
        self.assertEqual(recommendation['candidate_to_review'],'baseline')
        self.assertEqual(recommendation['equivalent_sampled_answers'],['alidns','baseline','dnspod'])

    def test_failed_fast_answers_and_duplicate_samples_cannot_win(self):
        files=self.files();samples=json.loads(files['samples.json'])
        for row in samples:
            if row['resolver']=='alidns':row.update({'http_code':403,'time_starttransfer':.001})
        files['samples.json']=research.encode(samples)
        self.assertEqual(research.summary(self.manifest(files),files)['recommendations'][0]['candidate_to_review'],'dnspod')
        samples.append(samples[0]);files['samples.json']=research.encode(samples)
        with self.assertRaises(ValueError):research.summary(self.manifest(files),files)

    def test_one_sample_or_missing_ip_coverage_not_complete(self):
        files=self.files();samples=json.loads(files['samples.json'])
        samples=[x for x in samples if x['resolver']!='alidns' or x['sample']!=4]
        files['samples.json']=research.encode(samples)
        report=research.summary(self.manifest(files),files)
        self.assertFalse(next(x for x in report['comparisons'] if x['resolver']=='alidns' and x['vantage']=='pi')['complete_success'])

    def write_run(self,root,files):
        run=root/'run';run.mkdir(mode=0o700)
        for name,data in files.items():
            (run/name).write_bytes(data);(run/name).chmod(0o600)
        (run/'manifest.json').write_bytes(research.encode(self.manifest(files)));(run/'manifest.json').chmod(0o600)
        return run

    def test_hash_permissions_and_traversal_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            run=self.write_run(Path(tmp),self.files());research.load_run(run)
            (run/'proxy.list').write_bytes(b'changed')
            with self.assertRaises(ValueError):research.load_run(run)
            manifest=json.loads((run/'manifest.json').read_text());manifest['files']['../secret']={'sha256':'a'*64,'bytes':1}
            (run/'manifest.json').write_bytes(research.encode(manifest))
            with self.assertRaises(ValueError):research.load_run(run)
        with tempfile.TemporaryDirectory() as tmp:
            run=self.write_run(Path(tmp),self.files());(run/'source.yaml').chmod(0o644)
            with self.assertRaises(ValueError):research.load_run(run)

    def test_stability_requires_end_evidence(self):
        files=self.files();files['state-after.json']=b'{}'
        with tempfile.TemporaryDirectory() as tmp:
            run=self.write_run(Path(tmp),files)
            with self.assertRaises(ValueError):research.load_run(run)

    def test_candidate_dry_run_never_runs_native_or_creates_output(self):
        files=self.files();manifest=self.manifest(files)
        with tempfile.TemporaryDirectory() as tmp,patch.object(research,'mirror_check',return_value={}),patch.object(research,'read_rules',return_value=['+.xiaohongshu.com']):
            output=Path(tmp)/'candidate'
            result=research.candidate(Path(tmp),manifest,files,'alidns',output,True)
            self.assertFalse(result['writes']);self.assertFalse(output.exists())

    def test_candidate_is_private_and_only_validation_copy_rewrites_paths(self):
        files=self.files();manifest=self.manifest(files)
        lock={'data_revision':'b'*40,'files':[{'path':research.CN_PATH,'sha256':'c'*64}]}
        def validate(core,path,home):
            data=json.loads(path.read_text())
            self.assertEqual(data['rule-providers']['china-services-pilot']['path'],str(home/'china-services.list'))
            self.assertTrue((home/'proxy.list').is_file())
        with tempfile.TemporaryDirectory() as tmp,patch.object(research,'mirror_check',return_value=lock),patch.object(research,'read_rules',return_value=['+.xiaohongshu.com']),patch('native_check.core_path',return_value=Path('/fixture/core')),patch('native_check.native_test',side_effect=validate):
            root=Path(tmp);run=self.write_run(root,files);out=root/'candidate'
            result=research.candidate(run,manifest,files,'alidns',out)
            self.assertFalse(result['deployable'])
            self.assertEqual(json.loads((out/'candidate.yaml').read_text())['rule-providers']['china-services-pilot']['path'],research.PROVIDER_PATH)
            self.assertTrue(all(x.stat().st_mode & 0o777==0o600 for x in out.iterdir()))
            with self.assertRaises(ValueError):research.candidate(run,manifest,files,'alidns',out)

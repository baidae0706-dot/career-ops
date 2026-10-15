import copy,json,unittest
from unittest.mock import patch
from delivery import live_candidate

class CompatibilityTests(unittest.TestCase):
 def setUp(self):
  self.config={'repo':'test/project'}
  self.req={'pr':147,'head_sha':'a'*40,'target_base_sha':'b'*40,'target_branch':'main'}
  self.pr={'headRefOid':'a'*40,'baseRefName':'main','state':'OPEN','isDraft':False,'mergeable':'MERGEABLE','statusCheckRollup':[{'status':'COMPLETED'}]}
  self.api={'head':{'sha':'a'*40},'base':{'sha':'b'*40,'ref':'main'}}
 def call(self):
  with patch('delivery.gh',return_value=copy.deepcopy(self.pr)),patch('delivery.output',return_value=json.dumps(self.api)):
   return live_candidate(self.config,self.req)
 def test_older_cli_preserves_identity_and_checks(self):
  result=self.call();self.assertEqual(result['baseRefOid'],'b'*40);self.assertEqual(result['statusCheckRollup'],self.pr['statusCheckRollup'])
 def test_target_base_change_rejected(self):
  self.api['base']['sha']='c'*40
  with self.assertRaisesRegex(RuntimeError,'differs from pinned'):self.call()
 def test_head_read_race_rejected(self):
  self.api['head']['sha']='c'*40
  with self.assertRaisesRegex(RuntimeError,'between metadata reads'):self.call()
 def test_target_branch_read_race_rejected(self):
  self.api['base']['ref']='other'
  with self.assertRaisesRegex(RuntimeError,'between metadata reads'):self.call()
 def test_missing_identity_is_not_accepted(self):
  del self.api['base']['sha']
  with self.assertRaises(KeyError):self.call()

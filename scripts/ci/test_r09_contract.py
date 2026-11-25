import unittest
from pathlib import Path
from unittest.mock import patch
import r09_contract as contract

class R09Wiring(unittest.TestCase):
    def test_current_tree(self): self.assertTrue(contract.verify())
    def test_removed_promise_refused(self):
        original=Path.read_text
        for path,tokens in contract.REQUIRED.items():
            for token in tokens:
                with self.subTest(path=path,token=token):
                    def mutated(file,*a,**k):
                        code=original(file,*a,**k)
                        return code.replace(token,'__REMOVED_R09__') if file==contract.ROOT/path else code
                    with patch.object(Path,'read_text',mutated),self.assertRaises(ValueError): contract.verify()
    def test_risk_paths_route_full(self):
        for glob in contract.RISK:
            path=glob.replace('**','r09_test.dart').replace('*','discovery.dart')
            with self.subTest(path=path): self.assertTrue(contract.policy.classify([path])['full_flutter'])
if __name__=='__main__': unittest.main()

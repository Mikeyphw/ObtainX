"""Named negative tests against the actual applied R08 source tree."""
import unittest
from pathlib import Path
from unittest.mock import patch
import r08_contract as contract

class R08SourceContractTest(unittest.TestCase):
    def test_real_source(self):
        self.assertTrue(contract.verify())

    def test_each_promise_wiring_is_required(self):
        original=Path.read_text
        for path,tokens in contract.REQUIRED.items():
            for token in tokens:
                with self.subTest(path=path,token=token):
                    def mutated(file,*args,**kwargs):
                        text=original(file,*args,**kwargs)
                        return text.replace(token,'__R08_REMOVED__') if file==contract.ROOT/path else text
                    with patch.object(Path,'read_text',mutated),self.assertRaises(ValueError):
                        contract.verify()

    def test_legacy_url_matching_rejected(self):
        original=Path.read_text
        def mutated(file,*args,**kwargs):
            text=original(file,*args,**kwargs)
            if file==contract.ROOT/'lib/providers/source_provider.dart':
                text+='\nreg.hasMatch(element.key) || reg.hasMatch(element.value)\n'
            return text
        with patch.object(Path,'read_text',mutated),self.assertRaises(ValueError):
            contract.verify()

if __name__=='__main__': unittest.main()

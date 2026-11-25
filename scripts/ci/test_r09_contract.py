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
    def test_analyzer_regressions_refused(self):
        original=Path.read_text
        old_patterns = (
            ('test/r09_artifact_inspection_test.dart', "const asset = MapEntry('x86.apk', 'https://example.org/apk');", "final asset = const MapEntry('x86.apk', 'https://example.org/apk');"),
            ('lib/components/generated_form_renderer.dart', "'r09BoundSourceUrl': ?boundUrl", "if (boundUrl != null) 'r09BoundSourceUrl': boundUrl"),
            ('lib/providers/apps_provider_install.dart', 'downloadOnly: pickAnyAsset).eligible))) {\n      return null;\n    }', 'downloadOnly: pickAnyAsset).eligible))) return null;'),
            ('lib/widgets/r04_actions_history_dialog.dart', 'if (row.canSelectAt(now())) {', 'if (row.canSelectAt(now()))'),
            ('lib/widgets/r04_actions_history_dialog.dart', 'Navigator.of(context).pop(row);\n                                } else {\n                                  setState(() {});', 'Navigator.of(context).pop(row);\n                                else setState(() {});'),
        )
        for path, fixed, old in old_patterns:
            with self.subTest(path=path, old=old):
                self.assertIn(fixed, original(contract.ROOT/path))
                def mutated(file,*args,**kwargs):
                    code=original(file,*args,**kwargs)
                    return code.replace(fixed,old) if file==contract.ROOT/path else code
                with patch.object(Path,'read_text',mutated),self.assertRaises(ValueError):
                    contract.verify()
    def test_risk_paths_route_full(self):
        for glob in contract.RISK:
            path=glob.replace('**','r09_test.dart').replace('*','discovery.dart')
            with self.subTest(path=path): self.assertTrue(contract.policy.classify([path])['full_flutter'])
if __name__=='__main__': unittest.main()

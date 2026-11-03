import unittest
from unittest.mock import patch
import openrouter_transport as t

class OfflineTransportTests(unittest.TestCase):
    def raw(self):
        return {'id':'fixture', 'model':t.MODEL_ID, 'usage':{'cost':'0.0123'}}
    def test_cost_is_reported_not_recalculated_with_direct_prices(self):
        raw=self.raw(); value=t.normalize(raw)
        self.assertEqual(value['_cost_receipt']['cost_usd'],'0.0123')
        self.assertNotIn('_cost_receipt',raw)
    def test_unknown_or_invalid_cost_fails_closed(self):
        for cost in [None, True, -1, 'NaN', 'Infinity', 'bad']:
            raw=self.raw();raw['usage']['cost']=cost
            with self.assertRaises(ValueError):t.compute_cost(raw)
    def test_both_network_entrypoints_block_before_network(self):
        with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('network')):
            for method in [t.query,t.model_metadata]:
                with self.assertRaises(RuntimeError):method()
    def test_payload_pins_provider_without_direct_only_fields(self):
        body=t.payload([{'role':'user','content':'fixture'}],{'id':t.MODEL_ID,'backend':'openrouter','provider':'openai','seed':42,'reasoning_effort':'high'})
        self.assertFalse(body['provider']['allow_fallbacks'])
        self.assertEqual(body['provider']['only'],['openai'])
        self.assertNotIn('prompt_cache_options',body)
        self.assertEqual(body['seed'],42)

if __name__=='__main__':unittest.main()

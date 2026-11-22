"""Portable tests of campaign/species/article and filtered overview (no dependencies)."""
import ast
from pathlib import Path
import unittest
SOURCE=Path(__file__).resolve().parents[1]/'backend'/'app'/'history.py'
tree=ast.parse(SOURCE.read_text())
functions=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in ('filtered_catalogue','overview')]
class Router:
 def get(self,path): return lambda f:f
def Query(default,**kwargs):return default
context={'router':Router(),'Query':Query,'os':__import__('os')}
exec(compile(ast.Module(body=functions,type_ignores=[]),str(SOURCE),'exec'),context)
filter_lots=context['filtered_catalogue'];overview=context['overview']
ITEMS=[
 dict(lot_code='13877',campaign='C25',species=['Tomate'],articles=['TOPGUN'],varieties=['Roma'],lot_refs=['RO-13877/25'],graft_refs=[]),
 dict(lot_code='13878',campaign='C25',species=['Tomate'],articles=['TOPGUN'],varieties=['Carolina'],lot_refs=['RO-13878/25'],graft_refs=[]),
 dict(lot_code='12345',campaign='C24',species=['Melon'],articles=['Orange'],varieties=['Galia'],lot_refs=['RO-12345/24'],graft_refs=[]),
 dict(lot_code='99999',campaign=None,species=[],articles=[],varieties=[],lot_refs=[],graft_refs=[]),
]
class FilterTests(unittest.TestCase):
 def setUp(self):
  context['catalogue']=lambda: ITEMS
  pi={'13877':[1,2], '13878':[1], '12345':[1]}
  di={'13877':[1,2,3], '12345':[1], '99999':[1]}
  gi={'13877':[1], '13878':[1]}
  context['indexes']=lambda:([],[],[],pi,di,gi)
 def test_combined(self):self.assertEqual([x['lot_code'] for x in filter_lots(ITEMS,'C25','Tomate','Roma')],['13877'])
 def test_campaign(self):self.assertEqual(len(filter_lots(ITEMS,'C24')),1)
 def test_unknown(self):self.assertEqual([x['lot_code'] for x in filter_lots(ITEMS,'__UNKNOWN__')],['99999'])
 def test_text_search(self):self.assertEqual([x['lot_code'] for x in filter_lots(ITEMS,'C25',search='carolina')],['13878'])
 def test_filtered_overview(self):
  d=overview('C25','Tomate','Roma')
  self.assertEqual((d['production_rows'],d['delivery_rows'],d['grafting_rows'],d['linked_lots'],d['scoped_lots']),(2,3,1,1,1))
  self.assertTrue(d['filtered'])
 def test_global_overview(self):
  d=overview()
  self.assertEqual((d['production_rows'],d['delivery_rows'],d['scoped_lots']),(4,5,4))
  self.assertFalse(d['filtered'])
if __name__=='__main__': unittest.main(verbosity=2)

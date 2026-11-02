from phys_adapter_base import Adapter
a=Adapter('P05')
for key in dir(a):
    if not key.startswith('_'):globals()[key]=getattr(a,key)

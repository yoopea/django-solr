from django.utils.importlib import import_module
from djangosolr.documents.util import escape

class Options(object):
    
    def __init__(self, meta):
        self.meta = meta
        self.model = None
        self.type = None
        self.fields = []
        self.pk = None
        
    def get_field(self, name):
        for field in self.fields:
            if field.name == name:
                return field
        return None
    
    def get_field_name(self, name):
        return escape('%s-%s' % (self.type, self.get_field(name).name,))
        
    def add_field(self, field):
        self.fields.append(field)
        if field.primary_key:
            self.pk = field
    
    def _contribute_to_class(self, cls, name):
        cls._meta = self
        self.name = cls.__name__.lower()
        if self.meta:
            meta_attrs = self.meta.__dict__.copy()
            for name in self.meta.__dict__:
                if name.startswith('_'):
                    del meta_attrs[name]
            for attr_name in ['model', 'type']:
                if attr_name in meta_attrs:
                    setattr(self, attr_name, meta_attrs.pop(attr_name))
                elif hasattr(self.meta, attr_name):
                    setattr(self, attr_name, getattr(self.meta, attr_name))
            
            if meta_attrs != {}:
                raise TypeError("'class Meta' got invalid attribute(s): %s" % ','.join(meta_attrs.keys()))
        if not self.type:
            self.type = self.name
        del self.meta
    
    def _prepare_class(self, model):
        from django.conf import settings
        mapping = settings.DJANGOSOLR_FIELD_MAPPING
        if model._meta.model:
            for df in model._meta.model._meta.local_fields:
                kwargs = dict(name=df.name, stored=True, indexed=True, multivalued=False, primary_key=df.primary_key)
                sc = df.__class__.__module__ + '.' + df.__class__.__name__
                f_module, f_classname = mapping[sc].rsplit('.', 1)
                f = getattr(import_module(f_module), f_classname)(**kwargs) 
                model._add_to_class(f.name, f)
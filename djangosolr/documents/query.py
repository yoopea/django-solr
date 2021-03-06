from django.utils import tree
import re

FILTER_CONTAINS = u'%(field)s:%(value)s'
FILTER_EXACT = u'%(field)s:"%(value)s"'
FILTER_COMPARE = {
    'gt': u'%(field)s:{%(value)s TO *}',
    'gte': u'%(field)s:[%(value)s TO *]',
    'lt': u'%(field)s:{* TO %(value)s}',
    'lte': u'%(field)s:[* TO %(value)s]',
}
FILTER_RANGE = {
    'range':   u'%(field)s:[%(from)s TO %(to)s]',
    'rangecc': u'%(field)s:[%(from)s TO %(to)s]',
    'rangeoc': u'(%(field)s:{%(from)s TO *} AND %(field)s:[* TO %(to)s])',
    'rangeco': u'(%(field)s:[%(from)s TO *] AND %(field)s:{* TO %(to)s})',
    'rangeoo': u'%(field)s:{%(from)s TO %(to)s}'
}
WHITESPACE_RE = re.compile(r'\s+')

class Q(tree.Node):
    
    AND = 'AND'
    OR = 'OR'
    default = AND

    def __init__(self, *args, **kwargs):
        super(Q, self).__init__(children=list(args) + kwargs.items())

    def _combine(self, other, conn):
        if not isinstance(other, Q):
            raise TypeError(other)
        obj = Q()
        obj.add(self, conn)
        obj.add(other, conn)
        return obj

    def __or__(self, other):
        return self._combine(other, self.OR)

    def __and__(self, other):
        return self._combine(other, self.AND)

    def __invert__(self):
        obj = Q()
        obj.add(self, self.AND)
        obj.negate()
        
    def get_query_string(self, meta):
        query = []
        for child in self.children:
            if isinstance(child, basestring):
                query.append(child)
            elif hasattr(child, 'get_query_string'):
                query.append(child.get_query_string(meta))
            else:                
                filterx, value = child
                fn, _, ft = filterx.partition('__')
                f = meta.get_field(fn)
                fn = meta.get_solr_field_name(fn)
                if not ft or ft == 'contains':
                    if isinstance(value, basestring):
                        queryt = []
                        for value in WHITESPACE_RE.split(value):
                            queryt.append(FILTER_CONTAINS % {'field': fn, 'value': f.prepare_to_query(value)})
                        s = u' AND '.join(queryt)
                        if len(queryt) > 1:
                            s = u'(%s)' % (s,)
                        query.append(s)
                    else:
                        query.append(FILTER_CONTAINS % {'field':fn, 'value': f.prepare_to_query(value)})
                elif ft == 'exact':
                    query.append(FILTER_EXACT % {'field': fn, 'value': f.prepare_to_query(value)})
                elif ft in FILTER_COMPARE:
                    value = u'"%s"' % (f.prepare_to_query(value),) if isinstance(value, basestring) else f.prepare_to_query(value)
                    query.append(FILTER_COMPARE[ft] % {'field': fn, 'value': value})
                elif ft in FILTER_RANGE:
                    value1, value2 = value
                    value1 = u'"%s"' % (f.prepare_to_query(value1),) if isinstance(value1, basestring) else f.prepare_to_query(value1)
                    value2 = u'"%s"' % (f.prepare_to_query(value2),) if isinstance(value2, basestring) else f.prepare_to_query(value2)
                    query.append(FILTER_RANGE[ft] % {'field': fn, 'from': value1, 'to': value2})
                elif ft == 'in':
                    query.append(u'(%s)' % (' OR '.join([u'%s:%s' % (fn, f.prepare_to_query(v),) for v in value]),))
                else:
                    raise NotImplementedError
        s = (u' %s ' % (self.connector,)).join(filter(lambda y: y, query))
        if self.negated:
            s = u'NOT (%s)' % (s,)
        elif len(self.children) > 1:
            s = u'(%s)' % (s,)
        return s
    
class Query(object):
    
    def __init__(self):
        self._q = Q()
        self._fq = Q()
        self._sort = []
        self._fl = []
        self._start = None
        self._rows = None
        self._params = []
        
    def clone(self):
        clone = Query()
        clone._q = self._q
        clone._fq = self._fq
        clone._sort.extend(self._sort)
        clone._fl.extend(self._fl)
        clone._start = self._start
        clone._rows = self._rows 
        clone._params.extend(self._params)
        return clone
    
    def q(self, *qs, **filters):
        for q in qs:
            self._q &= q
        if filters:
            self._q &= Q(**filters)
               
    def fq(self, *qs, **filters):
        for q in qs:
            self._fq &= q
        if filters:
            self._fq &= Q(**filters) 

    def fl(self, *fields):
        self._fl.extend(fields)
    
    def sort(self, *fields):
        self._sort.extend(fields)
    
    def raw(self, **kwargs):
        for k, v in kwargs.items():
            self._params.append((k,v,))
        
    def set_limits(self, start, stop):
        self._start = start
        if stop is not None:
            self._rows = stop - (self._start or 0)
        else:
            self._rows = None
            
    def get_query_string(self, meta):
        query = []
        
        #start/rows
        if self._start is not None:
            query.append(('start', self._start,))
        if self._rows is not None:
            query.append(('rows', self._rows,))

        #q
        if not self._q:
            self._q = Q('*:*')
        query.append(('q', self._q.get_query_string(meta),))
        
        #fq        
        self._fq &= Q('%s:%s' % (meta.get_solr_type_field(), meta.get_solr_type_value(),))
        query.append(('fq', self._fq.get_query_string(meta),))

        #sort
        if self._sort:
            sort = ','.join(['%s desc' % (meta.get_solr_field_name(field[1:]),) if field.startswith('-')
                             else '%s asc' % (meta.get_solr_field_name(field),)
                             for field in self._sort])
            query.append(('sort', sort,))
        
        #fl
        if self._fl:
            query.append(('fl', ','.join([meta.get_solr_field_name(f) for f in self._fl]),))
          
        #raw params
        query.extend(self._params)
        
        return query

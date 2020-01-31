class countCalls(object):
    """Decorator that keeps track of the number of times a function is called.
    ::
    
        >>> @countCalls
        ... def foo():
        ...     return "spam"
        ... 
        >>> for _ in range(10)
        ...     foo()
        ... 
        >>> foo.count()
        10
        >>> countCalls.counts()
        {'foo': 10}
    
    Found in the Pythod Decorator Library from http://wiki.python.org/moin web site.
    """

    instances = {}

    def __init__(self, func):
        self.func = func
        self.numcalls = 0
        countCalls.instances[func] = self

    def __call__(self, *args, **kwargs):
        self.numcalls += 1
        print(self.counts())
        return self.func(*args, **kwargs)

    def count(self):
        "Return the number of times this function was called."
        return countCalls.instances[self.func].numcalls

    @staticmethod
    def counts():
        "Return a dict of {function: # of calls} for all registered functions."
        return dict([(func.__name__, countCalls.instances[func].numcalls) for func in countCalls.instances])
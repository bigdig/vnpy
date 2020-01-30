# encoding: utf-8
import sys
sys.path.append('../')
sys.path.append('../../')
sys.path.append('../../vnpy/trader/')

from vnpy.trader.vtClientConsole import Agent

if __name__ == '__main__':
    d = Agent('/vtClientConsole.pid', True)

    if len(sys.argv) == 1:
        d.start(True) #foreground
    elif len(sys.argv) == 2:
        arg = sys.argv[1]
        if arg in ('start', 'stop', 'restart'):
            getattr(d, arg)()  
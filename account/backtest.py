# encoding: utf-8
'''
组合策略测试
'''
import sys
sys.path.append('../../')

from vnpy.app.cta_strategy.strategies import STRATEGY_CLASS

import argparse
import pandas as pd
import numpy as np
from datetime import datetime
from setup_logger import setup_logger
setup_logger(filename='logsBackTest/vnpy_{0}.log'.format(datetime.now().strftime('%m%d_%H%M')), debug=False)

def main(argv):
    # setup the argument parser
    arg_parser = argparse.ArgumentParser(description='backtest')
    arg_parser.add_argument('-m', '--mode',
                            required=False,
                            default='B',
                            help="set backtest mode(B or T)")
    arg_parser.add_argument('-d', '--days',
                            required=False,
                            default=1,
                            type = int,
                            help="set backtest days")

    arg_parser.add_argument('-sd', '--startDate',
                            required=False,
                            default='',
                            help="set backtest days")

    arg_parser.add_argument('-s', '--vtSymbol',
                            required=False,
                            default='rb1801',
                            help="set backtest vtSymbol")

    arg_parser.add_argument('-s2', '--vtSymbol2',
                            required=False,
                            default='',
                            help="set spread vtSymbol2")

    arg_parser.add_argument('-hd', '--historyDays',
                            required=False,
                            default=0,
                            type = int,
                            help="set history days")

    arg_parser.add_argument('-sf', '--settingFile',
                            required=False,
                            default='CTA_setting_multi.json',
                            help="setting file name")

    arg_parser.add_argument('-o', '--optimization',
                            required=False,
                            default=False,
                            type = bool,
                            help="parameter optimization")

    arg_parser.add_argument('-yappi', '--yappi',
                            required=False,
                            default=False,
                            type = bool,
                            help="yappi status")

    # parse arguments
    cmd = arg_parser.parse_args(argv)

    strategyClass = STRATEGY_CLASS.get("MultiStrategy", None)
    print(STRATEGY_CLASS)
    strategyClass.settingFile = cmd.settingFile      #设置配置文件
    strategyClass.vtSymbol = cmd.vtSymbol            #设置品种

    if cmd.yappi:
        import yappi
        yappi.set_clock_type("cpu")
        yappi.start()

    strategyClass.backtestingWithConfig(startDate = cmd.startDate, days = cmd.days, mode = cmd.mode,vtSymbol = cmd.vtSymbol, vtSymbol2 = cmd.vtSymbol2, historyDays = cmd.historyDays , optimization = cmd.optimization)

    if cmd.yappi:
        yappi.get_func_stats().print_all()
        yappi.get_thread_stats().print_all()

if __name__ == "__main__":
    main(sys.argv[1:])
    #main("-d 1 -s rb1905 -hd 0 -sf CTA_setting_Spread.json -s2 rb1910 -m T".split())


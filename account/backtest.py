# encoding: utf-8
'''
组合策略测试
'''
import sys
sys.path.append('../../')

from vnpy.app.cta_strategy.strategies.strategyMulti import MultiStrategy

import argparse
import pandas as pd
import numpy as np
from datetime import datetime
from setup_logger import setup_logger
setup_logger(filename='logsBackTest/vnpy_{0}.log'.format(datetime.now().strftime('%m%d_%H%M')), debug=False)

from vnpy.app.cta_strategy.backtesting import BacktestingEngine, OptimizationSetting
from datetime import datetime,date,timedelta
import time
import json
import traceback

########################################################################
'''
backtesting
'''
def backtesting(settingFile, kLineCycle = 30, vt_symbol = 'rb1801', vt_symbol2 = None, mode = 'B', startDate = None, days = 1, historyDays = 0, optimization = False):

    # 创建回测引擎
    engine = BacktestingEngine()
    
    # 设置回测用的数据起始日期
    if startDate:
        startDate = startDate
        endDate = datetime.strptime(startDate, '%Y%m%d') + timedelta(days)
    else:
        startDate = date.today() - timedelta(days + historyDays)
        endDate = date.today()

    engine.set_parameters(
        vt_symbol=vt_symbol,
        interval="1m",
        start= startDate,
        end=endDate,
        rate=1/10000,
        slippage=1,
        size=10,
        pricetick=1,
        capital=1_000_000,
    )

    setting = {}
    setting['vt_symbol'] = vt_symbol
    setting['kLineCycle'] = kLineCycle
    setting['settingFile'] = settingFile
    engine.add_strategy(MultiStrategy, setting)

    engine.load_data()
    engine.run_backtesting()
    df = engine.calculate_result()
    engine.calculate_statistics()
    #engine.show_chart()

    # 显示回测结果
    resultList = engine.showBacktestingResult()

    # try:
    #     engine.showDailyResult()
    # except:
    #     print ('-' * 20)
    #     print ('Failed to showDailyResult')
    #     #traceback.print_exc() 
    #     pass


    try:
        # 显示定单信息
        import pandas as pd
        orders = pd.DataFrame([i.__dict__ for i in resultList['resultList']])
        try:
            orders['holdTime'] = (orders.exitDt - orders.entryDt).astype('timedelta64[m]')
        except:
            pass
        pd.options.display.max_rows = 100
        pd.options.display.width = 300
        pd.options.display.precision = 2
        engine.output ('-' * 50)
        engine.output(str(orders))
    except:
        print ('-' * 20)
        print ('Failed to print result')
        #traceback.print_exc() 


    try:
        # 显示详细信息
        import pandas as pd
        from utils import plot_candles, plot_candles1
        import talib
        import numpy as np
        # analysis
        #engine.loadHistoryData()

        orders = pd.DataFrame([i.__dict__ for i in resultList['resultList']])
        pricing = pd.DataFrame(list(engine.history_data))
        print(pricing.symbol)

        #VPIN analysis
        # from .VPINAnalysis import VPINAnalysis
        # if len(pricing.index) > 1000:
        #     VPINAnalysis(pricing)

        atr = talib.ATR(pricing.high_price.values, pricing.low_price.values, pricing.close_price.values, 25)
        atr_ma = pd.DataFrame(atr).rolling(25).mean()[0].values
        technicals = {
            'rsi': talib.RSI(pricing.close_price.values, 4),
            'atr': atr,
            'atr-ma': atr_ma
        }
        technicals = {}
        plot_candles1(pricing, volume_bars=True, orders=orders, technicals=technicals)
    except:
        print ('-' * 20)
        print ('Failed to plot candles')
        traceback.print_exc() 

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

    arg_parser.add_argument('-s', '--vt_symbol',
                            required=False,
                            default='rb1801',
                            help="set backtest vt_symbol")

    arg_parser.add_argument('-s2', '--vt_symbol2',
                            required=False,
                            default='',
                            help="set spread vt_symbol2")

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

    if cmd.yappi:
        import yappi
        yappi.set_clock_type("cpu")
        yappi.start()

    backtesting(settingFile = cmd.settingFile, startDate = cmd.startDate, days = cmd.days, mode = cmd.mode,vt_symbol = cmd.vt_symbol, vt_symbol2 = cmd.vt_symbol2, historyDays = cmd.historyDays , optimization = cmd.optimization)

    if cmd.yappi:
        yappi.get_func_stats().print_all()
        yappi.get_thread_stats().print_all()

if __name__ == "__main__":
    main(sys.argv[1:])
    #main("-d 1 -s rb1905 -hd 0 -sf CTA_setting_Spread.json -s2 rb1910 -m T".split())


# encoding: UTF-8

'''
本文件包含了backtesting decorator。
'''
from vnpy.trader.app.ctaStrategy.ctaBacktesting import *
from datetime import datetime,date
import time
import json
import traceback
########################################################################
class stdoutfile(object):
    # temp stdout
    console=None
    fhandle=None

    # save the stdout when initial
    def __init__(self,fhandle):
        self.console=sys.stdout
        self.fhandle=fhandle

    # define write method to output to file and screen
    def write(self, string):
        self.console.write(string)
        self.fhandle.write(string)

    # reset the stdout
    def reset(self):
        sys.stdout=self.console

    def flush(self):
        pass

########################################################################
'''
backtesting decorator
'''
def backtesting(strategy):
    """
    A decorator to add backtesting
    """
    old_init = strategy.__init__

    def new_init(self, *args, **kwargs):
        old_init(self, *args, **kwargs)
        #parsley_form(self)


    def test():
        reload(sys)
        sys.setdefaultencoding('utf8')    

        print(u'save log to output.log ? (y/n)')
        input = raw_input('--> ')
        
        if input == 'y' or input == '':
            f=open("output.log",'w')
            sout = stdoutfile(f)
            sys.stdout=sout

        print(u'backtest BAR_MODE(B), TICK_MODE(T)')
        input = raw_input('--> ')
        if input == '':
            input = 'B'
        
        # 创建回测引擎
        engine = BacktestingEngine()
        
        # 设置引擎的回测模式为K线
        engine.setBacktestingMode(engine.TICK_MODE if input == 'T' else engine.BAR_MODE)
        # 设置使用的历史数据库
        engine.setDatabase(TICK_DB_NAME if input == 'T' else MINUTE_DB_NAME, 'rb1710')

        # 设置回测用的数据起始日期

        print(u'backtest today(t), this week(w), this month(m), this year(y), all years(a)')
        input = raw_input('--> ')
        if input == '':
            input = 't'

        startDate = None
        if input == 't':
            startDate = date.today() - timedelta(days=10) 
        elif input == 'w':
            startDate = date.today() - timedelta(days=17)
        elif input == 'm':
            startDate = date.today() - timedelta(days=40)
        elif input == 'y':
            startDate = date.today() - timedelta(days=375)
        else:
            startDate = date.today() - timedelta(days=10000)

        print(startDate.strftime('%Y%m%d'))
        engine.setStartDate(startDate.strftime('%Y%m%d'))
        
        # 设置产品相关参数
        #engine.setSlippage(0.2)     # 股指1跳
        #engine.setRate(0.3/10000)   # 万0.3
        #engine.setSize(300)         # 股指合约大小        
        engine.setSlippage(1)
        engine.setRate(1/10000)
        engine.setSize(10) 
        
        print(u'run optimization?(yes/no)')
        input = raw_input('--> ')
        if input == '':
            input = 'y'

        if input == 'n':
            # 在引擎中创建策略对象
            print(u'input kLineCycle number(default 12)')
            input = raw_input('--> ')
            if input == '':
                input = '18'
            
            d = {"kLineCycle":int(input)}
            engine.initStrategy(strategy, d)
            
            # 开始跑回测
            engine.runBacktesting()
            
            # 显示回测结果
            engine.showBacktestingResult()

            #for log in engine.logList:print(log)

        else:
            # 跑优化
            setting = OptimizationSetting()                 # 新建一个优化任务设置对象
            setting.setOptimizeTarget('capital')            # 设置优化排序的目标是策略净盈利
            #setting.addParameter('kkDev', 0.5, 2.0, 0.10)    # 增加第一个优化参数kkDev，起始0.5，结束1.5，步进1
            #setting.addParameter('stopLossPercent', 2, 3, 0.5)        # 增加第二个优化参数atrMa，起始20，结束30，步进1
            #setting.addParameter('rsiLength', 5)            # 增加一个固定数值的参数
            #setting.addParameter('kkLength',18,23,1)
            setting.addParameter('kLineCycle',5,31,1)
            
            # 性能测试环境：I7-3770，主频3.4G, 8核心，内存16G，Windows 7 专业版
            # 测试时还跑着一堆其他的程序，性能仅供参考
            import time    
            start = time.time()
            
            print(u'single(s) cpu or multi(m) cpus(may cause aliyun ssh offline)')
            input = raw_input('--> ')
            if input == 's':
                engine.runOptimization(strategy, setting) 
            else:     
                # 多进程优化，耗时：89秒
                engine.runParallelOptimization(strategy, setting) 
            
            print (u'耗时：%s' %(time.time()-start))



    #mode vtSymbol days kLineCyle
    def test1(kLineCycle = 30, vtSymbol = 'rb1801', vtSymbol2 = None, mode = 'B', startDate = None, days = 1, historyDays = 0, optimization = False):
        start = time.time()

        # 创建回测引擎
        engine = BacktestingEngine()
        
        # 设置引擎的回测模式为K线
        engine.setBacktestingMode(engine.TICK_MODE if mode == 'T' else engine.BAR_MODE)
        # 设置使用的历史数据库
        engine.setDatabase(TICK_DB_NAME if mode == 'T' else MINUTE_DB_NAME, vtSymbol)

        # 设置回测用的数据起始日期
        if startDate:
            engine.setStartDate(startDate,historyDays)
            endDate = datetime.strptime(startDate, '%Y%m%d') + timedelta(days)
            engine.setEndDate(endDate.strftime('%Y%m%d'))
        else:
            startDate = date.today() - timedelta(days + historyDays)
            engine.setStartDate(startDate.strftime('%Y%m%d'),historyDays)
        
        # 设置产品相关参数
        #engine.setSlippage(0.2)     # 股指1跳
        #engine.setRate(0.3/10000)   # 万0.3
        #engine.setSize(300)         # 股指合约大小        
        engine.setSlippage(1)
        engine.setRate(1.0/10000)
        engine.setSize(10)
        engine.setCapital(200000)
        
        # 原油
        if vtSymbol.find("sc") == 0:
            engine.setSlippage(0.1)
            engine.setSize(1000)
            engine.setPriceTick(0.1)
        if vtSymbol.find("ni") == 0:
            engine.setSlippage(10)
            engine.setSize(1)
            engine.setPriceTick(10)

        #------------------------------------------------------------------
        if optimization:
            # 跑优化
            setting = OptimizationSetting()                 # 新建一个优化任务设置对象
            setting.setOptimizeTarget('capital')            # 设置优化排序的目标是策略净盈利
            #setting.addParameter('kkDev', 0.5, 2.0, 0.10)    # 增加第一个优化参数kkDev，起始0.5，结束1.5，步进1
            #setting.addParameter('stopLossPercent', 2, 3, 0.5)        # 增加第二个优化参数atrMa，起始20，结束30，步进1
            setting.addParameter('vtSymbol', vtSymbol)            # 增加一个固定数值的参数
            setting.addParameter('kLineCycle',10,20,1)
            setting.addParameter('exitOnTopRtnPips',0.007,0.01,0.001)
            setting.addParameter('halfTime',60,120,60)
            
            # 性能测试环境：I7-3770，主频3.4G, 8核心，内存16G，Windows 7 专业版
            # 测试时还跑着一堆其他的程序，性能仅供参考

            print(u'single(s) cpu or multi(m) cpus(may cause aliyun ssh offline)')
            opt = input('--> ')
            if opt == 's':
                engine.runOptimization(strategy, setting) 
            else:     
                # 多进程优化，耗时：89秒
                engine.runParallelOptimization(strategy, setting) 
            
            print (u'耗时：%s' %(time.time()-start))
            return
        #------------------------------------------------------------------

        setting = {}
        setting['vtSymbol'] = vtSymbol
        setting['kLineCycle'] = kLineCycle
        engine.initStrategy(strategy,setting=setting)
        
        # 开始跑回测
        if vtSymbol2:
            # spread test
            engine.runBacktesting([vtSymbol,vtSymbol2])
        else:
            engine.runBacktesting()
        
        # 显示回测结果
        resultList = engine.showBacktestingResult()

        try:
            engine.showDailyResult()
        except:
            print ('-' * 20)
            print ('Failed to showDailyResult')
            #traceback.print_exc() 
            pass


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
            pricing = pd.DataFrame(list(engine.dbCursor))

            #VPIN analysis
            from .VPINAnalysis import VPINAnalysis
            if len(pricing.index) > 1000:
                VPINAnalysis(pricing)

            atr = talib.ATR(pricing.high.values, pricing.low.values, pricing.close.values, 25)
            atr_ma = pd.DataFrame(atr).rolling(25).mean()[0].values
            technicals = {
                'rsi': talib.RSI(pricing.close.values, 4),
                'atr': atr,
                'atr-ma': atr_ma
            }
            technicals = {}
            plot_candles1(pricing, volume_bars=True, orders=orders, technicals=technicals)
        except:
            print ('-' * 20)
            print ('Failed to plot candles')
            traceback.print_exc() 



    strategy.__init__ = new_init
    strategy.backtesting = staticmethod(test)
    strategy.backtestingWithConfig = staticmethod(test1)
    return strategy
# encoding: UTF-8
'''
本文件包含了CTA引擎中的策略开发用模板。
添加了一些基本的策略属性，变量。不做下单逻辑
'''

from .SharedArrayManager import getSharedArrayManager
# from vnpy.trader.vtFunction import timeit

from vnpy.app.cta_strategy import (
    BarData,
    TickData,
    BarGenerator,
    ArrayManager,
)

from .ctaTemplate_5 import CtaTemplate_5

########################################################################
class CtaTemplate_6(CtaTemplate_5):
    """
    add bar manager
    """

    className = 'CtaTemplate_6'
    author = u'rxg'

    # 基本变量
    initDays = 20  # 初始化数据所用的天数
    kLineCycle = 6  #Bar line cycle
    KLineSeconds = 60  #生成X秒的K线
    marketTradeValue = 0  #策略的交易市值
    arraySize = 100

    parameters = CtaTemplate_5.parameters + \
                [
                 'className',
                 'author',
                 'vt_symbol',
                 'kLineCycle',
                 'initDays',
                 'debugMode',
                 'KLineSeconds',
                 'arraySize'
                 ]

    varList = CtaTemplate_5.variables + \
                [
                ]

    #----------------------------------------------------------------------
    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """"""
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)
        print("-----")
        print(self.kLineCycle)
        self.bm = BarGenerator(self.on_bar, self.kLineCycle,
                             self.onXminBar)  # 创建K线合成器对象

        self.bm.xsec = self.KLineSeconds  #按指定X秒生成K线

        #self.am = ArrayManager(size=self.arraySize)
        self.am = getSharedArrayManager(self.vt_symbol, self.kLineCycle,
                                        self.KLineSeconds, self.arraySize)

        self.bm60 = BarGenerator(self.on_bar,60,self.on60MinBar)
        self.am60 = getSharedArrayManager(self.vt_symbol, 60,
                                        self.KLineSeconds, 100)

    #----------------------------------------------------------------------
    # @timeit
    def on_init(self):
        """初始化策略（必须由用户继承实现）"""
        self.writeCtaLog(u'策略初始化')

        # 载入历史数据，并采用回放计算的方式初始化策略数值
        self.load_bar(self.initDays)

        if hasattr(self,'signal'):
            if hasattr(self.signal, 'am'):
                if not self.signal.am.inited:
                    self.writeCtaLog(u'%s策略信号加载初始数据不足' % self.strategy_name)
                    print(u'%s策略信号加载初始数据不足 ' % self.strategy_name, self.initDays)

        if not self.am.inited:
            print(u'%s策略加载初始数据不足 ' % self.strategy_name, self.kLineCycle, self.initDays)

        if not self.am60.inited:
            print(u'%s策略加载60 Min Bar 初始数据不足  ' % self.strategy_name, self.initDays)

        self.putEvent()

    #----------------------------------------------------------------------
    def on_start(self):
        """启动策略（必须由用户继承实现）"""
        self.write_log(u'策略启动')
        self.putEvent()

    #----------------------------------------------------------------------
    def on_stop(self):
        """停止策略（必须由用户继承实现）"""
        self.cancel_all()
        self.write_log(u'停止')
        self.putEvent()

    #----------------------------------------------------------------------
    def on_tick(self, tick:TickData):
        """收到行情TICK推送（必须由用户继承实现）"""
        super(CtaTemplate_6, self).on_tick(tick)
        self.bm.update_tick(tick)

    #----------------------------------------------------------------------
    def on_bar(self, bar:BarData):
        '''处理分钟数据'''
        super(CtaTemplate_6, self).on_bar(bar)
        self.bm.update_bar(bar)
        self.bm60.update_bar(bar)

    #----------------------------------------------------------------------
    def onXminBar(self, bar):
        """收到X分钟K线"""
        # 保存K线数据
        am = self.am
        am.update_bar(bar)
        if not am.inited:
            return

    def on60MinBar(self, bar):
        """收到X分钟K线"""
        self.am60.update_bar(bar)
        if not self.am60.inited:
            return

    #----------------------------------------------------------------------
    def getVolatility(self, volatilityTime = 60):
        """收到X分钟K线"""
        # 保存K线数据
        return (self.am.atr(50)/self.lastPrice)*((volatilityTime/self.kLineCycle)**0.5)
